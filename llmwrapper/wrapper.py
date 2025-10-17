# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""A caching wrapper around a Google wrapper around the Gemini API."""

# Import standard libraries
from abc import ABC, abstractmethod
from copy import deepcopy
from itertools import count
import logging
import time

# Import external libraries
from google import genai
from jsonschema import validate
from jsonschema.exceptions import ValidationError as JSONValidationError
from lxml.etree import XMLSyntaxError
from mako.template import Template
import mdformat

# Import local libraries
from . import jsonschema, yaml, utils

# Initialize a logger
LOGGER = logging.getLogger('wrapper')


# Error definitions
class LLMError(RuntimeError):
    """A common class for LLM errors."""

class ValidationError(LLMError):
    """A validation error."""


class LLModel(ABC):
    """A generic large language model."""

    def __init__(self, queries, cache, tries=5, cooldown=20):
        self.queries = queries
        self.cache = cache
        self.tries = tries
        self.cooldown = cooldown
        cache.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def defaults(self):
        """Provide default query settings."""

    @abstractmethod
    def basequery(self, prompt):
        """Query LLM."""

    def query(self, query, slot, validators, **kwargs):
        """Resolve prompt, cache an LLM query."""
        prompt = load_prompt(self.queries, query, **kwargs)
        prompt = JSONObject(self.defaults()) | prompt

        # Use the cache if exists and not stale
        hash = utils.deephash(prompt)
        path = self.cache/f'{query}-{slot}.yaml'
        if path.exists():
            cached = load_yaml(path)
            if cached['hash'] == hash:
                return cached['response']

        # Query LLM, reflow text parts
        LOGGER.info(f'generating {query}-{slot}')
        response, timer, stats = self.retry(prompt, validators)

        # Prepare a cache object
        prompt['hash'] = hash, None
        prompt['response'] = response, prompt.get('schema')
        prompt['duration'] = timer, {'type': 'integer', 'unit': 'ms'}
        prompt['usage_stats'] = stats, True
        del prompt['schema']

        # Cache the results
        dump_yaml(prompt, path)
        return response


    def retry(self, prompt, validators):
        for i in count():
            try:
                timer = time.monotonic()
                response, stats = self.basequery(prompt)
                timer = int((time.monotonic() - timer)*1000)  # ms
                if 'mimeType' not in prompt['schema']:
                    validate(response, prompt['schema'])
                    response = utils.reflow(response)  # can raise SVG errors
                for check in validators:
                    check(response)
                return response, timer, stats
            except (LLMError, JSONValidationError, XMLSyntaxError) as err:
                if i == self.tries - 1:
                    raise
                LOGGER.warn(f'retry {i + 1}: got {repr(err)}')
                time.sleep(self.cooldown)


def load_prompt(path, query, **kwargs):
    """Load and instantiate a YAML prompt from a collection."""
    with open(path, 'r') as file:
        schema, prompt = yaml.find(file, query=query)

    # Instantiate and reflow the template
    prompt['prompt'] = Template(prompt['prompt']).render(**kwargs)
    prompt['prompt'] = mdformat.text(
        prompt['prompt'],
        options = {'wrap': 80, 'number': True},
        extensions = {'dollarmath', 'footnote', 'table'},
    ).rstrip()

    # Expand the schema
    prompt['schema'] = jsonschema.load(prompt.get('schema', 'str'))
    return JSONObject(prompt, schema)


def dump_yaml(prompt, path):
    """Save a prompt-response pair to a YAML-like file, dump included images."""
    # Dump the image, if present
    response_schema = prompt.schema['properties']['response']
    if 'mimeType' in response_schema:
        _, ext = response_schema['mimeType'].split('/')
        img_path = path.with_suffix('.' + ext)
        with open(img_path, 'wb') as file:
            file.write(prompt['response'])
        # Replace the image data with a relative reference to the image
        prompt = prompt.copy()
        prompt['response'] = img_path.name, response_schema

    # Dump the prompt
    with open(path, 'wt') as file:
        yaml.dump(prompt.schema, [prompt], file)


def load_yaml(path):
    """Load a prompt-response pair from a YAML-like file, load included images."""
    # Load the prompt
    with open(path, 'rt') as file:
        schema, [prompt] = yaml.load(file)

    # Load the image, if present
    if 'mimeType' in schema['properties']['response']:
        with open(path.parent/prompt['response'], 'rb') as file:
            prompt['response'] = file.read()
    return prompt


# A very hacky solution to avoid a few lines of boiler-plate; I'll come to regret it
class JSONObject(dict):
    """A wrapper around a dictionary with an attached JSON schema."""

    def __init__(self, obj, schema=None):
        super().__init__(obj)
        if schema is None:
            self.schema = jsonschema.deduce(obj)
        else:
            self.schema = schema

    def __or__(self, other):
        return JSONObject(super().__or__(other), {
            'type': 'object',
            'properties': self.schema['properties'] | other.schema['properties'],
        })

    def __delitem__(self, key):
        super().__delitem__(key)
        del self.schema['properties'][key]

    def __setitem__(self, key, value):
        value, schema = value
        if schema is None:
            schema = jsonschema.deduce(value)
        super().__setitem__(key, value)
        self.schema['properties'][key] = schema

    def copy(self):
        return JSONObject(super().copy(), deepcopy(self.schema))


class Gemini(LLModel):
    """A specialization of LLModel to Gemini."""

    def __init__(self, key, model, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.client = genai.Client(api_key=key)

    def defaults(self):
        """Provide default query settings."""
        return {
            'model': self.model,
        }

    def basequery(self, prompt):
        """Query LLM."""
        schema = {
            'response_mime_type': 'application/json',
            'response_schema': prompt['schema'],
        } if prompt['schema']['type'] != 'string' else {}

        try:
            response = self.client.models.generate_content(
                model = prompt['model'],
                contents = prompt['prompt'],
                config = {
                    **schema,
                },
            )
            match prompt['schema']:
                case {'type': 'string', 'mimeType': mime_type}:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data is not None and part.inline_data.mime_type == mime_type:
                            content = part.inline_data.data
                            break
                    else:
                        raise LLMError(f'{mime_type} not found')
                case {'type': 'string'}:
                    content = response.text
                case _:
                    content = response.parsed
            return content, utils.upcast(response.usage_metadata)
        except genai.errors.ClientError as err:
            raise LLMError(err.status) from err
        except genai.errors.ServerError as err:
            raise LLMError(err.status) from err


# A handful of additional validators

def chk_sum(key, total, threshold=0.05):
    """Check that values at keys roughly sum up to total."""
    def validator(response):
        summed = sum(obj[key] for obj in response)
        if abs(summed/total - 1) > threshold:
            raise ValidationError('chk_sum validation failed')
    return validator


def chk_range(key, min, max):
    """Check that values at keys are unique and fall within range."""
    def validator(response):
        values = [obj[key] for obj in response]
        if len(set(values)) < len(values):
            raise ValidationError()
        if not all(min <= v <= max for v in values):
            raise ValidationError('chk_range validation failed')
    return validator


def chk_words(min, max):
    """Check the total word count falls withing range."""
    def validator(response):
        if not min <= utils.count_words(response) <= max:
            raise ValidationError('chk_words validation failed')
    return validator

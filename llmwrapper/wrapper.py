# Copyright (c) 2025 Andrey Dubovik <andrei at dubovik dot eu>

"""A caching wrapper around a Google wrapper around the Gemini API."""

# Import standard libraries
from abc import ABC, abstractmethod
import time

# Import external libraries
from google import genai
from jsonschema import validate
from mako.template import Template
import mdformat

# Import local libraries
from . import jsonschema, yaml, utils


# Error definitions
class LLMError(RuntimeError):
    """A common class for LLM errors."""

class ValidationError(LLMError):
    """A validation error."""


class LLModel(ABC):
    """A generic large language model."""

    def __init__(self, queries, cache):
        self.queries = queries
        self.cache = cache
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
            with open(path, 'r') as file:
                _, [cached] = yaml.load(file)
            if cached['hash'] == hash:
                return cached['response']

        # Query LLM, reflow text parts
        response, timer, stats = self.retry(prompt, validators)

        # Prepare a cache object
        prompt['hash'] = hash, None
        prompt['response'] = response, prompt.get('schema')
        prompt['duration'] = timer, {'type': 'integer', 'unit': 'ms'}
        prompt['usage_stats'] = stats, True
        del prompt['schema']

        # Cache the results
        with open(path, 'w') as file:
            yaml.dump(prompt.schema, [prompt], file)
        return response


    def retry(self, prompt, validators):
        # TODO: add retries, passing through for the time being
        timer = time.monotonic()
        response, stats = self.basequery(prompt)
        timer = int((time.monotonic() - timer)*1000)  # ms
        validate(response, prompt['schema'])
        for check in validators:
            check(response)
        response = utils.reflow(response)  # can raise SVG errors
        return response, timer, stats


def load_prompt(path, query, **kwargs):
    """Load and instantiate a YAML prompt from a collection."""
    with open(path, 'r') as file:
        schema, prompt = yaml.find(file, query=query)

    # Instantiate and reflow the template
    prompt['prompt'] = Template(prompt['prompt']).render(**kwargs)
    prompt['prompt'] = mdformat.text(
        prompt['prompt'],
        options={'wrap': 80, 'number': True},
    ).rstrip()

    # Expand the schema
    prompt['schema'] = jsonschema.load(prompt.get('schema', 'str'))
    return JSONObject(prompt, schema)


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
            if prompt['schema']['type'] == 'string':
                content = response.text
            else:
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
            raise ValidationError()
    return validator


def chk_range(key, min, max):
    """Check that values at keys are unique and fall within range."""
    def validator(response):
        values = [obj[key] for obj in response]
        if len(set(values)) < len(values):
            raise ValidationError()
        if not all(min <= v <= max for v in values):
            raise ValidationError()
    return validator


def chk_words(min, max):
    """Check the total word count falls withing range."""
    def validator(response):
        if not min <= utils.count_words(response) <= max:
            raise ValidationError()
    return validator

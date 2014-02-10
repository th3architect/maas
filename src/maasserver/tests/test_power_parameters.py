# Copyright 2012, 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for power parameters."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from django import forms
import jsonschema
from maasserver.config_forms import DictCharField
from maasserver.fields import MACAddressFormField
from maasserver.power_parameters import (
    get_power_type_parameters_from_json,
    make_form_field,
    make_json_field,
    POWER_TYPE_PARAMETERS,
    POWER_TYPE_PARAMETER_FIELD_SCHEMA,
    )
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from provisioningserver.enum import get_power_types
from provisioningserver.power.poweraction import PowerAction
from testtools.matchers import (
    AllMatch,
    ContainsAll,
    Equals,
    IsInstance,
    MatchesStructure,
    )


class TestPowerParameterDeclaration(MAASServerTestCase):

    def test_POWER_TYPE_PARAMETERS_is_dict_with_power_type_keys(self):
        power_types = set(get_power_types().keys())
        self.assertIsInstance(POWER_TYPE_PARAMETERS, dict)
        # The empty parameters is a special value just for the UI so
        # remove it.
        params = POWER_TYPE_PARAMETERS.copy()
        del params['']
        self.assertThat(power_types, ContainsAll(params))

    def test_POWER_TYPE_PARAMETERS_values_are_DictCharField(self):
        self.assertThat(
            POWER_TYPE_PARAMETERS.values(),
            AllMatch(IsInstance(DictCharField)))

    def test_POWER_TYPE_PARAMETERS_DictCharField_objects_have_skip_check(self):
        self.assertThat(
            POWER_TYPE_PARAMETERS.values(),
            AllMatch(MatchesStructure(skip_check=Equals(True))))


class TestPowerActionRendering(MAASServerTestCase):
    """Test that the power templates can be rendered."""

    scenarios = [
        (name, {'power_type': name})
        for name in list(get_power_types())
    ]

    def make_random_parameters(self, power_change="on"):
        params = {'power_change': power_change}
        param_definition = POWER_TYPE_PARAMETERS[self.power_type]
        for name, field in param_definition.field_dict.items():
            params[name] = factory.make_name(name)
        return params

    def test_render_template(self):
        params = self.make_random_parameters()
        node = factory.make_node(power_type=self.power_type)
        params.update(node.get_effective_power_parameters())
        action = PowerAction(self.power_type)
        script = action.render_template(action.get_template(), **params)
        # The real check is that the rendering went fine.
        self.assertIsInstance(script, bytes)


class TestGetPowerTypeParametersFromJSON(MAASServerTestCase):
    """Test that get_power_type_parametrs_from_json."""

    def test_validates_json_power_type_parameters(self):
        invalid_parameters = [{
            'name': 'invalid_power_type',
            'fields': 'nothing to see here',
        }]
        self.assertRaises(
            jsonschema.ValidationError, get_power_type_parameters_from_json,
            invalid_parameters)

    def test_includes_empty_power_type(self):
        json_parameters = [{
            'name': 'something',
            'fields': [{
                'name': 'some_field',
                'label': 'Some Field',
                'field_type': 'string',
                'required': False,
            }],
        }]
        power_type_parameters = get_power_type_parameters_from_json(
            json_parameters)
        self.assertEqual(['', 'something'], power_type_parameters.keys())

    def test_creates_dict_char_fields(self):
        json_parameters = [{
            'name': 'something',
            'fields': [{
                'name': 'some_field',
                'label': 'Some Field',
                'field_type': 'string',
                'required': False,
            }],
        }]
        power_type_parameters = get_power_type_parameters_from_json(
            json_parameters)
        for name, field in power_type_parameters.items():
            self.assertIsInstance(field, DictCharField)


class TestMakeFormField(MAASServerTestCase):
    """Test that make_form_field() converts JSON fields to Django."""

    def test_creates_char_field_for_strings(self):
        json_field = {
            'name': 'some_field',
            'label': 'Some Field',
            'field_type': 'string',
            'required': False,
        }
        django_field = make_form_field(json_field)
        self.assertIsInstance(django_field, forms.CharField)

    def test_creates_choice_field_for_choices(self):
        json_field = {
            'name': 'some_field',
            'label': 'Some Field',
            'field_type': 'choice',
            'choices': [
                ['choice-one', 'Choice One'],
                ['choice-two', 'Choice Two'],
            ],
            'default': 'choice-one',
            'required': False,
        }
        django_field = make_form_field(json_field)
        self.assertIsInstance(django_field, forms.ChoiceField)
        self.assertEqual(json_field['choices'], django_field.choices)
        self.assertEqual(json_field['default'], django_field.initial)

    def test_creates_mac_address_field_for_mac_addresses(self):
        json_field = {
            'name': 'some_field',
            'label': 'Some Field',
            'field_type': 'mac_address',
            'required': False,
        }
        django_field = make_form_field(json_field)
        self.assertIsInstance(django_field, MACAddressFormField)

    def test_sets_properties_on_form_field(self):
        json_field = {
            'name': 'some_field',
            'label': 'Some Field',
            'field_type': 'string',
            'required': False,
        }
        django_field = make_form_field(json_field)
        self.assertEqual(
            (json_field['label'], json_field['required']),
            (django_field.label, django_field.required))


class TestMakeJSONField(MAASServerTestCase):
    """Test that make_json_field() creates JSON-verifiable fields."""

    def test_returns_json_verifiable_dict(self):
        json_field = make_json_field('some_field', 'Some Label')
        jsonschema.validate(json_field, POWER_TYPE_PARAMETER_FIELD_SCHEMA)

    def test_provides_sane_default_values(self):
        json_field = make_json_field('some_field', 'Some Label')
        expected_field = {
            'name': 'some_field',
            'label': 'Some Label',
            'required': False,
            'field_type': 'string',
            'choices': [],
            'default': '',
        }
        self.assertEqual(expected_field, json_field)

    def test_sets_field_values(self):
        expected_field = {
            'name': 'yet_another_field',
            'label': 'Can I stop writing tests now?',
            'required': True,
            'field_type': 'string',
            'choices': [
                ['spam', 'Spam'],
                ['eggs', 'Eggs'],
            ],
            'default': 'spam',
        }
        json_field = make_json_field(**expected_field)
        self.assertEqual(expected_field, json_field)

    def test_validates_choices(self):
        self.assertRaises(
            jsonschema.ValidationError, make_json_field,
            'some_field', 'Some Label', choices="Nonsense")

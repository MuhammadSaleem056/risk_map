from qgis.utils import iface
# from qgis.core import QgsExpression (only when in QGIS python)
from math import inf
from enum import Enum
from collections import defaultdict
from functools import reduce
import operator


class Mode(Enum):
    Normalized = 1
    Rules = 2
    Matches = 3

class Type(Enum):
    Hazard = 1
    SocialVulnerability = 2
    StructuralVulnerability = 3


COL_PGA = 'pga_mean' # low --|AVG|-- medium --|MAX|-- high #Peak Ground Acceleration values from KNMI
COL_NUM_SIDES = 'num_sides'
COL_NUM_BAG_UNITS = 'bag_units_count'
COL_NUM_NEIGHBOURS = 'num_neighbours'
COL_HEIGHT = 'height' # ignore
COL_FLOORS = 'floors' # literature; 1 floor - 0.5, 2+ - 1
COL_BUILT_YEAR = 'built_year' # it works, rationale in the report
COL_USAGE = 'usage' #

# results
COL_RISK = 'risk'
COL_HAZARD = 'risk_hazard'
COL_STRUCTURAL_VULNERABILITY = 'risk_structural'
COL_SOCIAL_VULNERABILITY = 'risk_social'

CONDITIONS = {
    COL_PGA: {
        'mode': Mode.Rules,
        'type': Type.Hazard,
        'weight': 1,
        'default_value': 0,
        'rules': [
            {'min': -inf,   'max': 0.05,       'value': 0.3, },
            {'min': 0.05,   'max': 0.15,       'value': 0.6, },
            {'min': 0.15,   'max': +inf,       'value': 1.0, },
        ],
    },
    # irrregularity does not make sense in the case of Groningen tremors
    COL_NUM_SIDES: {
        'mode': Mode.Rules,
        'type': Type.StructuralVulnerability,
        'weight': 0,
        'default_value': 0.5,
        'rules': [
            {'min': -inf,   'max': 5,       'value': 1, },
            {'min': 5,      'max': 10,     'value': 0.5, },
            {'min': 10,      'max': inf,     'value': 0.2, },
        ],
    },
    # social
    COL_NUM_BAG_UNITS: {
        'mode': Mode.Rules,
        'type': Type.SocialVulnerability,
        'weight': 1,
        'default_value': 0.5,
        'rules': [
            {'min': -inf,   'max': 1,       'value': 0, },
            {'min': 1,      'max': 2,       'value': 0.1, },
            {'min': 2,      'max': 3,       'value': 0.2, },
            {'min': 3,      'max': 4,       'value': 0.3, },
            {'min': 4,      'max': 5,       'value': 0.4, },
            {'min': 5,      'max': inf,     'value': 1, },
        ],
    },
    COL_NUM_NEIGHBOURS: {
        'mode': Mode.Normalized,
        'type': Type.StructuralVulnerability,
        'weight': 1,
        'default_value': 0.1,
        'rules': [],
    },
    COL_HEIGHT: {
        'mode': Mode.Rules,
        'type': Type.StructuralVulnerability,
        'weight': 0,
        'default_value': 0,
        'rules': [
            {'min': -inf,   'max': +inf,      'value': 1, },
        ],
    },
    COL_FLOORS: {
        'mode': Mode.Rules,
        'type': Type.StructuralVulnerability,
        'weight': 2,
        'default_value': 0,
        'rules': [
            {'min': -inf,   'max': 1,       'value': 0.5, },
            {'min': 1,      'max': inf,     'value': 1, },
        ],
    },
    # should not assume the buildings in the 60s and 70 to be not good, cause of baby boomers
    COL_BUILT_YEAR: {
        'mode': Mode.Rules,
        'type': Type.StructuralVulnerability,
        'weight': 4,
        'default_value': 0,
        'rules': [
            {'min': -inf,   'max': 1800,       'value': 1, },
            {'min': 1800,   'max': 1900,       'value': 0.9, },
            {'min': 1900,   'max': 1920,       'value': 0.8, },
            {'min': 1920,   'max': 1930,       'value': 0.7, },
            {'min': 1930,   'max': 1940,       'value': 0.6, },
            {'min': 1940,   'max': 1950,       'value': 0.5, },
            {'min': 1950,   'max': 1960,       'value': 0.5, },
            {'min': 1960,   'max': 1970,       'value': 0.7, },
            {'min': 1970,   'max': 1980,       'value': 0.7, },
            {'min': 1980,   'max': 1990,       'value': 0.6, },
            {'min': 1990,   'max': 2000,       'value': 0.5, },
            {'min': 2000,   'max': 2010,       'value': 0.4, },
            {'min': 2010,   'max': 2017,       'value': 0.3, },
            {'min': 2017,   'max': inf,         'value': 0, },
        ],
    },
    COL_USAGE: {
        'mode': Mode.Matches,
        'type': Type.SocialVulnerability,
        'weight': 2,
        'default_value': 0,
        'matches': {
            'medical': 1,
            'educational': 1,

            'public': 0.8,
            'office': 0.5,
            'commercial': 0.5,

            'residential': 0.9,

            'sports': 0.5,
            'other': 0.2,
            'industrial': 0.2,
        }
    },
}

# STOP TOUCHING HERE!!!
##################################################

layer = iface.activeLayer()
fields = layer.fields()

layer.startEditing()

if not layer.isEditable():
    raise Exception('Layer is not in editable mode')


# calculate aggregates
weights_map: defaultdict = defaultdict(float)
aggregate_cols = []

for col, condition in CONDITIONS.items():
    weights_map[condition['type']] += condition['weight']

    if condition['mode'] == Mode.Normalized:
        aggregate_cols.append(col)

aggregates = dict()

for col in aggregate_cols:
    col_idx = fields.indexOf(col)

    assert col_idx != -1

    aggregates[col] = {
        'col_idx': col_idx,
        'min': layer.minimumValue(col_idx),
        'max': layer.maximumValue(col_idx),
    }

    print('"%s" is in range: %d - %d' % (col, aggregates[col]['min'], aggregates[col]['max']))


def normalize(min_value, max_value, value):
    return (value - min_value) / (max_value - min_value)


for f in layer.getFeatures('bag_available IS TRUE'):
    result_map: defaultdict = defaultdict(list)

    for col, condition in CONDITIONS.items():
        col_idx = fields.indexOf(col)

        assert col_idx >= 0, 'No columns with such name %s' % col

        attr_val = f[col]
        result = condition.get('default_value')

        if condition['mode'] == Mode.Normalized:
            result = normalize(aggregates[col]['min'], aggregates[col]['max'], attr_val)
        elif condition['mode'] == Mode.Matches:
            assert 'matches' in condition

            result = condition['matches'].get(attr_val, condition.get('default_value'))
        elif condition['mode'] == Mode.Rules:
            assert 'rules' in condition

            is_rule_satisfied = False

            for rule in condition['rules']:
                if attr_val >= rule['min'] and attr_val < rule['max']:
                    is_rule_satisfied = True
                    result = rule['value']
                    break

            if not is_rule_satisfied:
                print('WARNING: no rule satisfied for col "%s"' % col)

        else:
            raise Exception('Oopsie, unknown mode')

        weighted_result = condition['weight'] / weights_map[condition['type']] * result
        result_map[condition['type']].append(weighted_result)

    # if f.id() > 100:
    #     raise Exception('Stop')

    # if f[COL_NUM_BAG_UNITS] != 0:
    #     print(result_map[Type.Exposure], f[COL_NUM_BAG_UNITS])

    risk_arguments = [sum(values) for values in result_map.values()]
    risk = reduce(operator.mul, risk_arguments, 1)

    # print(fields.indexOf(COL_HAZARD), result_map[Type.Hazard])
    # print((f.id(), fields.indexOf(COL_HAZARD), result_map[Type.Hazard]))

    layer.changeAttributeValue(f.id(), fields.indexOf(COL_RISK), risk)
    layer.changeAttributeValue(f.id(), fields.indexOf(COL_HAZARD), sum(result_map[Type.Hazard]))
    layer.changeAttributeValue(f.id(), fields.indexOf(COL_SOCIAL_VULNERABILITY), sum(result_map[Type.SocialVulnerability]))
    layer.changeAttributeValue(f.id(), fields.indexOf(COL_STRUCTURAL_VULNERABILITY), sum(result_map[Type.StructuralVulnerability]))


# layer.commitChanges()
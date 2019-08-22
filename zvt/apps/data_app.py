# -*- coding: utf-8 -*-

import dash_core_components as dcc
import dash_html_components as html
from dash import dash
from dash.dependencies import Input, Output, State

from zvdata.chart import Drawer
from zvdata.domain import global_providers, get_schemas, get_schema_by_name, get_schema_columns
from zvdata.normal_data import NormalData
from zvdata.reader import DataReader
from zvdata.utils.pd_utils import df_is_not_null
from zvdata.utils.time_utils import now_pd_timestamp, TIME_FORMAT_DAY
from zvt.api.common import has_report_period, get_important_column
from zvt.app import app
from zvt.settings import SAMPLE_STOCK_CODES

current_readers = {}

current_df = None


def gen_reader_id(provider, schema_name):
    return f'{provider}_{schema_name}'


def get_current_df():
    df = None
    for reader in current_readers.values():
        if df is None:
            df = reader.data_df
        else:
            df = df.join(reader.data_df)

    return df


layout = html.Div(
    [
        html.Div(
            [
                # provider selector
                dcc.Dropdown(
                    id='provider_selector',
                    placeholder='select provider',
                    options=[{'label': provider, 'value': provider} for provider in
                             global_providers]),

                # schema selector
                dcc.Dropdown(id='schema_selector', placeholder='select schema'),

                # column selector
                html.Div(id='schema_column_selector_container', children=None),

                # codes filter
                dcc.Input(id='input_code_filter', type='text', value=','.join(SAMPLE_STOCK_CODES),
                          style={'width': '400px'}),

                # time range filter
                dcc.DatePickerRange(
                    id='date-picker-range',
                    start_date='2009-01-01',
                    end_date=now_pd_timestamp(),
                    display_format=TIME_FORMAT_DAY
                ),

                # load data for table
                html.Button('load data', id='btn_load_data', n_clicks_timestamp=0),

                # reader list
                # dcc.Dropdown(
                #     id='reader_list',
                #     options=[
                #         {'label': reader, 'value': reader} for reader in current_readers
                #     ],
                #     value=current_readers.keys(),
                #     multi=True
                # ),

                # table container
                # html.Div(id='data_table_container', children=None),

                html.Div(id='table_type_label', children=None),

                html.Div(
                    [
                        html.Div([dcc.Dropdown(id='intent_selector')],
                                 style={'width': '50%', 'display': 'inline-block'}),
                        html.Div([dcc.Dropdown(id='chart-selector')],
                                 style={'width': '50%', 'display': 'inline-block'})
                    ]
                ),
                html.Div(id='chart-container', children=None)
            ])
    ]
)


@app.callback(
    Output('schema_selector', 'options'),
    [Input('provider_selector', 'value')])
def update_schema_selector(provider):
    if provider:
        return [{'label': schema.__name__, 'value': schema.__name__} for schema in
                get_schemas(provider=provider)]
    raise dash.exceptions.PreventUpdate()


@app.callback(
    Output('schema_column_selector_container', 'children'),
    [Input('schema_selector', 'value')],
    state=[State('provider_selector', 'value')])
def update_column_selector(schema_name, provider):
    if provider and schema_name:
        schema = get_schema_by_name(name=schema_name)
        cols = get_schema_columns(schema=schema)
        return dcc.Dropdown(
            id='schema_column_selector',
            options=[
                {'label': col, 'value': col} for col in cols
            ],
            value=get_important_column(schema_name=schema_name),
            multi=True
        )
    raise dash.exceptions.PreventUpdate()


@app.callback(
    [Output('table_type_label', 'children'),
     Output('intent_selector', 'options'),
     Output('intent_selector', 'value')],
    [Input('btn_load_data', 'n_clicks')],
    state=[State('provider_selector', 'value'),
           State('schema_selector', 'value'),
           State('schema_column_selector', 'value'),
           State('input_code_filter', 'value'),
           State('date-picker-range', 'start_date'),
           State('date-picker-range', 'end_date')])
def update_data_table(n_clicks, provider, schema_name, columns, codes: str, start_date, end_date):
    if n_clicks and provider and columns and schema_name:
        reader_id = gen_reader_id(provider=provider, schema_name=schema_name)

        if reader_id in current_readers:
            return f'clear:{reader_id} then reselect!', [
                {'label': 'compare_self', 'value': 'compare_self'}], 'compare_self'

        # TODO:better way to get time_field
        if has_report_period(schema_name=schema_name):
            time_field = 'report_date'
        else:
            time_field = 'timestamp'

        data_reader = DataReader(data_schema=get_schema_by_name(schema_name), provider=provider, codes=codes,
                                 columns=columns, start_timestamp=start_date, end_timestamp=end_date,
                                 time_field=time_field)

        current_readers[reader_id] = data_reader

        df = get_current_df()

        if not df_is_not_null(df):
            return 'no data,please reselect!', [{'label': 'compare_self', 'value': 'compare_self'}], 'compare_self'

        normal_data = NormalData(df=df)

        intents = normal_data.get_intents()

        intent_options = [
            {'label': intent.value, 'value': intent.value} for intent in intents
        ]

        intent_value = intents[0].value

        return normal_data.get_table_type(), intent_options, intent_value

    raise dash.exceptions.PreventUpdate()


@app.callback(
    [Output('chart-selector', 'options'),
     Output('chart-selector', 'value')],
    [Input('intent_selector', 'value')])
def update_chart_selector(intent):
    if intent:
        charts = NormalData.get_charts_by_intent(intent=intent)
        options = [
            {'label': chart.value, 'value': chart.value} for chart in charts
        ]
        value = charts[0].value

        return options, value
    raise dash.exceptions.PreventUpdate()


operators_df = [['ge ', '>='],
                ['le ', '<='],
                ['lt ', '<'],
                ['gt ', '>'],
                ['ne ', '!='],
                ['eq ', '='],
                ['contains '],
                ['datestartswith ']]

operators_sql = [['>= ', '>='],
                 ['<= ', '<='],
                 ['< ', '<'],
                 ['> ', '>'],
                 ['!= ', '!='],
                 ['== ', '='],
                 ['contains '],
                 ['datestartswith ']]


def split_filter_part(filter_part, operators=operators_sql):
    for operator_type in operators:
        for operator in operator_type:
            if operator in filter_part:
                name_part, value_part = filter_part.split(operator, 1)
                name = name_part[name_part.find('{') + 1: name_part.rfind('}')]

                value_part = value_part.strip()
                v0 = value_part[0]
                if (v0 == value_part[-1] and v0 in ("'", '"', '`')):
                    value = value_part[1: -1].replace('\\' + v0, v0)
                else:
                    try:
                        value = float(value_part)
                    except ValueError:
                        value = value_part

                # word operators need spaces after them in the filter string,
                # but we don't want these later
                return name, operator_type[0].strip(), value

    return [None] * 3


@app.callback(
    Output('chart-container', "children"),
    [Input('chart-selector', "value")])
def update_graph(chart):
    if chart:
        df = get_current_df()

        graph_data, graph_layout = Drawer(data=NormalData(df)).draw(chart=chart, render=None)

        return dcc.Graph(
            id='chart-content',
            figure={
                'data': graph_data,
                'layout': graph_layout
            }
        )

    raise dash.exceptions.PreventUpdate()

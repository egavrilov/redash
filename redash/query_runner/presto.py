import json

from redash.utils import JSONEncoder
from redash.query_runner import *

import logging
logger = logging.getLogger(__name__)

from collections import defaultdict

try:
    from pyhive import presto
    enabled = True

except ImportError:
    enabled = False

PRESTO_TYPES_MAPPING = {
    "integer": TYPE_INTEGER,
    "tinyint": TYPE_INTEGER,
    "smallint": TYPE_INTEGER,
    "long": TYPE_INTEGER,
    "bigint": TYPE_INTEGER,
    "float": TYPE_FLOAT,
    "double": TYPE_FLOAT,
    "boolean": TYPE_BOOLEAN,
    "string": TYPE_STRING,
    "varchar": TYPE_STRING,
    "date": TYPE_DATE,
}


class Presto(BaseQueryRunner):
    @classmethod
    def configuration_schema(cls):
        return {
            'type': 'object',
            'properties': {
                'host': {
                    'type': 'string'
                },
                'port': {
                    'type': 'number'
                },
                'schema': {
                    'type': 'string'
                },
                'catalog': {
                    'type': 'string'
                },
                'username': {
                    'type': 'string'
                }
            },
            'required': ['host']
        }

    @classmethod
    def enabled(cls):
        return enabled

    @classmethod
    def annotate_query(cls):
        return False

    @classmethod
    def type(cls):
        return "presto"

    def __init__(self, configuration):
        super(Presto, self).__init__(configuration)

    def get_schema(self, get_stats=False):
        schema = {}
        query = """
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema in ('bi', 'default', 'applift_api_production')
        ORDER BY table_schema, table_name, column_name asc
        """

        results, error = self.run_query(query)

        if error is not None:
            raise Exception("Failed getting schema.")

        results = json.loads(results)

        for row in results['rows']:
            if row['table_schema'] != 'public':
                table_name = '{}.{}'.format(row['table_schema'], row['table_name'])
            else:
                table_name = row['table_name']

            if table_name not in schema:
                schema[table_name] = {'name': table_name, 'columns': []}

            schema[table_name]['columns'].append(row['column_name'])

        return schema.values()

    def run_query(self, query, *redash_user):
        redash_user = redash_user[0]
        connection = presto.connect(
                host=self.configuration.get('host', ''),
                port=self.configuration.get('port', 8080),
                username=(redash_user if redash_user else 'app') + '-redash',
                catalog=self.configuration.get('catalog', 'hive'),
                schema=self.configuration.get('schema', 'default'))

        cursor = connection.cursor()

        if redash_user[0:5] not in ('Admin','Simon', 'app'):
            query = query.rstrip().lower()
            if query.find('select ') != -1:
                query = query + ' limit 2000'

        try:
            cursor.execute(query)
            column_tuples = [(i[0], PRESTO_TYPES_MAPPING.get(i[1], None)) for i in cursor.description]
            columns = self.fetch_columns(column_tuples)
            rows = [dict(zip(([c['name'] for c in columns]), r)) for i, r in enumerate(cursor.fetchall())]
            data = {'columns': columns, 'rows': rows}
            json_data = json.dumps(data, cls=JSONEncoder)
            error = None
        except Exception, ex:
            json_data = None
            error = ex.message

        return json_data, error

register(Presto)

"""Per-plugin default configs for create_query and create_datasource. Keyed by
plugin packageName (e.g. "restapi-plugin", "postgres-plugin"). The defaults are
sensible starting points the LLM can override."""


QUERY_ACTION_CONFIG_DEFAULTS: dict[str, dict] = {
    "restapi-plugin": {
        "httpMethod": "GET",
        "path": "/",
        "headers": [],
        "queryParameters": [],
        "timeoutInMillisecond": 10000,
        "encodeParamsToggle": True,
    },
    "graphql-plugin": {
        "httpMethod": "POST",
        "path": "",
        "headers": [{"key": "Content-Type", "value": "application/json"}],
        "queryParameters": [],
        "body": "",
        "timeoutInMillisecond": 10000,
        "encodeParamsToggle": True,
    },
    "postgres-plugin": {"body": "SELECT 1;"},
    "mysql-plugin": {"body": "SELECT 1;"},
    "mssql-plugin": {"body": "SELECT 1;"},
    "redshift-plugin": {"body": "SELECT 1;"},
    "snowflake-plugin": {"body": "SELECT 1;"},
    "oracle-plugin": {"body": "SELECT 1 FROM DUAL;"},
    "mongo-plugin": {
        "formData": {
            "command": {"data": "FIND"},
            "find": {
                "query": {"data": "{}"},
                "limit": {"data": "10"},
                "sort": {"data": ""},
                "projection": {"data": ""},
                "skip": {"data": "0"},
            },
            "smartSubstitution": {"data": True},
        }
    },
}


DATASOURCE_CONFIG_DEFAULTS: dict[str, dict] = {
    "restapi-plugin": {
        "url": "",
        "headers": [],
        "queryParameters": [],
    },
    "graphql-plugin": {
        "url": "",
        "headers": [],
        "queryParameters": [],
    },
    "postgres-plugin": {
        "endpoints": [{"host": "", "port": 5432}],
        "authentication": {
            "authenticationType": "dbAuth",
            "databaseName": "",
            "username": "",
            "password": "",
        },
        "connection": {"mode": "READ_WRITE", "ssl": {"authType": "DEFAULT"}},
    },
    "mysql-plugin": {
        "endpoints": [{"host": "", "port": 3306}],
        "authentication": {
            "authenticationType": "dbAuth",
            "databaseName": "",
            "username": "",
            "password": "",
        },
        "connection": {"mode": "READ_WRITE", "ssl": {"authType": "DEFAULT"}},
    },
    "mssql-plugin": {
        "endpoints": [{"host": "", "port": 1433}],
        "authentication": {
            "authenticationType": "dbAuth",
            "databaseName": "",
            "username": "",
            "password": "",
        },
        "connection": {"mode": "READ_WRITE", "ssl": {"authType": "DEFAULT"}},
    },
    "mongo-plugin": {
        "endpoints": [{"host": "", "port": 27017}],
        "authentication": {
            "authenticationType": "scramSha1",
            "databaseName": "",
            "username": "",
            "password": "",
        },
        "connection": {"mode": "READ_WRITE", "ssl": {"authType": "DEFAULT"}},
    },
}

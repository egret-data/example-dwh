"""sqlfluff only: stands in for the dbt_utils package macros that the jinja templater cannot load."""


def generate_surrogate_key(columns):
    return " || ".join(f"cast({column} as varchar)" for column in columns)

import duckdb


def run_sql_catch_error(conn, sql: str):
    # Remove any backtics from the string
    sql = sql.replace("`", "")

    # If there are multiple statements, only run the first one
    sql = sql.split(";")[0]

    try:

        output = conn.sql(sql)

        if output is None:
            rendered_output = "No output"
        else:
            try:
                results_as_python_objects = output.fetchall()
                rendered_rows = []
                for row in results_as_python_objects:
                    if len(row) == 1:
                        rendered_rows.append(str(row[0]))
                    else:
                        rendered_rows.append(','.join(str(x) for x in row))

                rendered_data = '\n'.join(rendered_rows)
                rendered_output = ','.join(output.columns) + '\n' + rendered_data
            except AttributeError:
                rendered_output = str(output)
        return rendered_output
    except duckdb.ProgrammingError as e:
        return str(e)
    except duckdb.Error as e:
        return str(e)
    # except Exception as e:
    #     return str(e)
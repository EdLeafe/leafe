import time

from flask import abort, g, redirect, render_template, request, url_for

import utils


class SearchObj:
    def __init__(self, form=None):
        self.form = form
        self.results = []
        self.statement = ""
        self.elapsed = 0.0
        self.parts = []
        self.search_terms = []
        self.params = []
        self.statement_parts = []
        self.exception = ""
        self.strict = True

    def strictify(self, val):
        if self.strict:
            if not val.startswith("^"):
                val = "^{}".format(val)
            if not val.endswith("$"):
                val = "{}$".format(val)
        return val

    def process_term(self, term, field=None):
        val = self.form.get(term)
        field = field or term
        if val:
            self.parts.append("{} REGEXP %s".format(field))
            self.search_terms.append(val)
            self.params.append(self.strictify(val))
            self.statement_parts.append("{} matches '{}'".format(term, val))

    def search(self):
        if not self.form:
            return
        self.process_term("zipcode", "postal_code")
        self.process_term("city")
        self.process_term("state")

        where_clause = ""
        if self.parts:
            where_clause = "where {}".format(" and ".join(self.parts))
        self.statement = ", ".join(self.statement_parts)
        sql = "select * from zip {} order by postal_code limit 100;".format(where_clause)
        crs = utils.get_cursor()
        print("SQL", sql)
        print("PRMS", self.params)
        start = time.time()
        try:
            crs.execute(sql, self.params)
            self.results = crs.fetchall()
        except utils.PymysqlInternalError:
            terms = ", ".join(self.search_terms)
            self.exception = f"Search failed: illegal regex expression: '{terms}'"
        self.elapsed = time.time() - start


def run_search():
    search_obj = SearchObj(request.form)
    search_obj.search()
    return search_obj


def show():
    g.show_results = request.method == "POST"
    if g.show_results:
        search_obj = run_search()
        g.results = search_obj.results
        g.query = search_obj.statement
        g.num_results = len(g.results)
        g.elapsed = round(search_obj.elapsed, 4)
        g.exception = search_obj.exception
    else:
        g.results = []
        g.query = ""
        g.num_results = 0
        g.elapsed = 0.0
        g.exception = ""
    return render_template("zipcodes.html")

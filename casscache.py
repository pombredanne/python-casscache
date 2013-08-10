from cassandra.cluster import Cluster, Session
from cassandra.query import ValueSequence

def _execute_many(self, statements):
    futures = []
    results = []

    for statement in statements:
        futures.append(self.execute_async(statement))

    for future in futures:
        try:
            results.append(future.result())
        except Exception:
            results.append(None)

    return results

Session.execute_many = _execute_many


class Client(object):
    def __init__(self, servers, **kwargs):
        hosts, port = set(), '9042'
        for server in servers:
            host, port = server.split(':', 1)
            hosts.add(host)

        self._cluster = Cluster(hosts, port=int(port), **kwargs)
        self._session = self._cluster.connect()

        self.keyspace = "cache"
        self.column_family = "memcached"

        self._session.set_keyspace(self.keyspace)

        # Prepare all of the necessary statements beforehand
        self._GET = self._session.prepare("SELECT value, flags FROM %s WHERE key = ? LIMIT 1" % self.column_family)
        self._SET = self._session.prepare("INSERT INTO %s (key, value, flags) VALUES (?, ?, ?)" % self.column_family)
        # Cannot be prepared with a dynamic TTL pre C* 2.0
        # See https://issues.apache.org/jira/browse/CASSANDRA-4450
        self._SET_TTL = "INSERT INTO %s (key, value, flags) VALUES (?, ?, ?) USING TTL %%d" % self.column_family

    def get(self, key):
        statement = self._GET
        return self._handle_row(self._session.execute(statement.bind((key,))))

    def get_multi(self, keys):
        statement = self._GET
        return map(self._handle_row, self._session.execute_many((statement.bind((key,)) for key in keys)))

    def set(self, key, value, ttl=0):
        if ttl == 0:
            statement = self._SET
        else:
            statement = self._session.prepare(self._SET_TTL % ttl)
        self._session.execute(statement.bind((key, value, 0)))
        return True

    def set_multi(self, keys):
        pass

    def delete(self, key):
        query = "DELETE FROM %s WHERE key = ?" % self.column_family

    def delete_multi(self, keys):
        query = "DELETE FROM %s WHERE key IN ?" % self.column_family

    def disconnect_all(self):
        self._cluster.shutdown()

    def get_stats(self, *args, **kwargs):
        """ No support for this in C* """
        return []

    def get_slabs(self, *args, **kwargs):
        return []

    def flush_all(self):
        query = "TRUNCATE %s" % self.column_family
        self._session.execute(query)

    def _handle_row(self, rows):
        try:
            return rows[0].value
        except (IndexError, TypeError):
            return None
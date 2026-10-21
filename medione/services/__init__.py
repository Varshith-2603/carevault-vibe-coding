"""Data services. Every public function takes the signed-in ``user_id`` and checks
ownership in SQL before reading or writing, so the UI cannot reach another
account's data by passing a different id."""

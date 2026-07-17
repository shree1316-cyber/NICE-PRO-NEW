import sqlite3

DB_NAME = "nice.db"


class Database:

    def __init__(self):

        self.conn = sqlite3.connect(DB_NAME)

        self.cur = self.conn.cursor()

        self.create_tables()

    def create_tables(self):

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS ticks(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            symbol TEXT,

            ltp REAL,

            volume INTEGER,

            bid REAL,

            ask REAL,

            tick_time TEXT
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            symbol TEXT,

            side TEXT,

            entry REAL,

            exit REAL,

            pnl REAL,

            reason TEXT,

            trade_time TEXT
        )
        """)

        self.conn.commit()

    def insert_tick(
        self,
        symbol,
        ltp,
        volume,
        bid,
        ask,
        tick_time,
    ):

        self.cur.execute(
            """
            INSERT INTO ticks(
                symbol,
                ltp,
                volume,
                bid,
                ask,
                tick_time
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                symbol,
                ltp,
                volume,
                bid,
                ask,
                tick_time,
            ),
        )

        self.conn.commit()

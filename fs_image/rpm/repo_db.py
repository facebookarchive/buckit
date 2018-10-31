#!/usr/bin/env python3
import enum


class SQLDialect(enum.Enum):
    SQLITE3 = 'sqlite3'
    MYSQL = 'mysql'

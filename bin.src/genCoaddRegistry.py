#!/usr/bin/env python

#
# LSST Data Management System
# Copyright 2008, 2009, 2010 LSST Corporation.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#

import glob
from optparse import OptionParser
import os
import re
import shutil
import sqlite3
import sys


def process(dirList, inputRegistry, outputRegistry="registry.sqlite3"):
    if os.path.exists(outputRegistry):
        print("Output registry exists; will not overwrite.", file=sys.stderr)
        sys.exit(1)
    if inputRegistry is not None:
        if not os.path.exists(inputRegistry):
            print("Input registry does not exist.", file=sys.stderr)
            sys.exit(1)
        shutil.copy(inputRegistry, outputRegistry)

    conn = sqlite3.connect(outputRegistry)

    done = {}
    if inputRegistry is None:
        # Create tables in new output registry.
        cmd = """CREATE TABLE raw (id INTEGER PRIMARY KEY AUTOINCREMENT,
            run INT, filter TEXT, camcol INT, field INT)"""
        # cmd += ", unique(run, filter, camcol, field))"
        conn.execute(cmd)
        cmd = "CREATE TABLE raw_skyTile (id INTEGER, skyTile INTEGER)"
        # cmd += ", unique(id, skyTile), foreign key(id) references raw(id))"
        conn.execute(cmd)
    else:
        cmd = """SELECT run || '_B' || filter ||
            '_C' || camcol || '_F' || field FROM raw"""
        for row in conn.execute(cmd):
            done[row[0]] = True

    try:
        for dir in dirList:
            for filterDir in glob.iglob(os.path.join(dir, "*")):
                processBand(filterDir, conn, done)
    finally:
        print("Cleaning up...", file=sys.stderr)
        conn.execute("CREATE INDEX ix_skyTile_id ON raw_skyTile (id)")
        conn.execute("CREATE INDEX ix_skyTile_tile ON raw_skyTile (skyTile)")
        conn.commit()
        conn.close()


def processBand(filterDir, conn, done):
    nProcessed = 0
    nSkipped = 0
    nUnrecognized = 0
    print(filterDir, "... started", file=sys.stderr)
    for fits in glob.iglob(
            os.path.join(filterDir, "fpC*_ts_coaddNorm_NN.fit.gz")):
        m = re.search(r'/([ugriz])/fpC-(\d{6})-\1(\d)-(\d{4})_ts_coaddNorm_NN.fit.gz', fits)
        if not m:
            print("Warning: Unrecognized file:", fits, file=sys.stderr)
            nUnrecognized += 1
            continue

        (filter, run, camcol, field) = m.groups()
        camcol = int(camcol)
        run = int(run)
        field = int(field)
        key = "%d_B%s_C%d_F%d" % (run, filter, camcol, field)
        if key in done:
            nSkipped += 1
            continue

        conn.execute("""INSERT INTO raw VALUES
            (NULL, ?, ?, ?, ?)""", (run, filter, camcol, field))

        nProcessed += 1
        if nProcessed % 100 == 0:
            conn.commit()

    conn.commit()
    print(filterDir,
          "... %d processed, %d skipped, %d unrecognized" %
          (nProcessed, nSkipped, nUnrecognized), file=sys.stderr)


if __name__ == "__main__":
    parser = OptionParser(usage="""%prog [options] DIR ...

DIR should contain a directory per filter containing coadd pieces.""")
    parser.add_option("-i", dest="inputRegistry", help="input registry")
    parser.add_option("-o", dest="outputRegistry", default="registry.sqlite3",
                      help="output registry (default=registry.sqlite3)")
    (options, args) = parser.parse_args()
    if len(args) < 1:
        parser.error("Missing directory argument(s)")
    process(args, options.inputRegistry, options.outputRegistry)

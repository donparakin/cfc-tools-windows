
import pyodbc
import openpyxl
import sys, pathlib, datetime


def update(members_xlsx, fields_xlsx, cfc_mdb, cfc_mdb_pw):
    msg_failed = 'FAILED!  Fix the error and re-run'
    failed = False
    steps = [
        _check_cfc_mdb_file(cfc_mdb),
        _process_members(members_xlsx, cfc_mdb, cfc_mdb_pw),
        # _process_fields(fields_xlsx, cfc_mdb, cfc_mdb_pw),
    ]
    try:
        for step in steps:
            if failed:
                break
            for msg in step:
                if msg is False:
                    failed = True
                    break
                else:
                    yield msg
    except:
        failed = True
        excp = sys.exc_info()
        emsg = f'{"-"*64}\nEXCEPTION: {excp[0]}\n'
        emsg += f'{excp[1]}\n{"-"*64}\n'
        yield emsg
    if failed:
        yield f'\nFAILED!  Fix error and re-run'
    else:
        yield f'\nSUCCESS!  All processing completed'


# ======================================================================
def _check_cfc_mdb_file(cfc_mdb):
    yield f'Updating CFC database:\n - File: {cfc_mdb}\n'
    emsg = _is_file(cfc_mdb)
    if type(emsg) == str:
        yield f' - {emsg}'
        yield False


# ======================================================================
def _process_members(members_xlsx, cfc_mdb, cfc_mdb_pw):
    ws_name = 'Data'
    ws_key = 'MID'
    mdb_key = '(tbd)'

    yield f'Reading from "All Members" report:\n - File: {members_xlsx}\n'

    emsg = _is_file(members_xlsx)
    if type(emsg) == str:
        yield f' - {emsg}'
        yield False
        return

    mdb = MDB(cfc_mdb, cfc_mdb_pw, 'Membership Information', 'NUMBER')
    n_read, n_updates, ws_new = 0, 0, []
    xlsx = XLSX(members_xlsx, ws_name)

    clog = open('zzz/data/cmu.changes.txt', 'w')
    for ws_row in xlsx.get_all():
        n_read += 1
        # if n_read < 10123:
        #     continue
        # if n_read > 10126:
        #     break

        if int(ws_row[ws_key]) < 100000:
            continue
        ws_row = _to_mdb_format(members_row=ws_row)

        mdb_row = mdb.get_id(ws_row['NUMBER'])
        if mdb_row is None:
            ws_new.append(ws_row)
            continue

        unequal_cols = _get_unequal_cols(mdb_row, ws_row)
        if len(unequal_cols) > 0:
            n_updates += 1
            clog.write(f'{ws_row["NUMBER"]} unequal: {unequal_cols}\n')
            # print(f'{ws_row["NUMBER"]} unequal: {unequal_cols}')
        if n_read % 10000 == 0:
            yield f'   ... {n_read:,} read; {n_updates:,} changes; {len(ws_new)} additions\n'
    yield f'   Finished: {n_read} read; {n_updates:,} changes; {len(ws_new)} additions\n'
    clog.close()


# ======================================================================
def _process_fields(fields_xlsx, cfc_mdb, cfc_mdb_pw):
    yield f'Reading "Members and Fields (NGB)" report:\n - File: {fields_xlsx}\n'
    yield f'   UNDER CONSTRUCTION; Nothing Processed'


# ======================================================================
# Shared Functions
# ======================================================================
def _is_file(filename):
    if not filename:
        return f'Error: File not specified\n'
    fp = pathlib.Path(filename)
    if not fp.exists():
        return f'Error: File not found: {filename}\n'
    if not fp.is_file():
        return f'Error: Must be a file: {filename}\n'
    return True


def _to_mdb_format(members_row=None, fields_row=None):
    mdb = {}
    if members_row:
        # Has: MID, First Name, Last Name, Email Address, Date of Birth, Gender,
        #       Address Line 1, Address Line 2, Town, County, Postcode, Country,
        #       Member State, Membership, Membership Expiry, Primary Club, Additional Clubs
        r = members_row
        mdb['NUMBER'] = _fmt_val(r['MID'], type=float)                # float
        mdb['FIRST'] = _fmt_val(r['First Name'], type=str)
        mdb['LAST'] = _fmt_val(r['Last Name'], type=str)
        g = _fmt_val(r['Gender'], type=str)
        mdb['SEX'] = 'M' if g == 'Male' else 'F' if g == 'Female' else ''
        mdb['ADDRESS'] = _fmt_val(r['Address Line 1'], type=str)
        mdb['CITY'] = _fmt_val(r['Town'], type=str)
        mdb['PROV'] = _province_to_pp(r['County'])
        mdb['BIRTHDATE'] = r['Date of Birth']               # datetime
        mdb['EXPIRY'] = r['Membership Expiry']              # datetime
        mdb['Email'] = _fmt_val(r['Email Address'], type=str)
        mdb['POSTCODE'] = _fmt_val(r['Postcode'], type=str)
    elif fields_row:
        # Has: MID, Firstname, Lastname, Category, Expiry,
        #       Additional Info - FIDE Membership Id, Additional Info - Provincial Affiliation
        r = fields_row
        mdb['NUMBER'] = float(r['MID'] or 0)
        mdb['FIDE NUMBER'] = _fmt_val(r['Additional Info - FIDE Membership Id'], type=float)
    return mdb


def _fmt_val(val, type=None):
    if type == str:
        val = str(val or '').strip()
    elif type == float:
        try:
            val = str(val or '').strip()
            val = float(val)
        except:
            val = None
    return val


_dt_high = datetime.datetime(2080, 1, 1)
_dt_low = datetime.datetime(1961, 12, 31)
def _get_unequal_cols(mdb_row, ws_row):
    unequal_cols = []
    for ws_key, ws_val in ws_row.items():
        if type(ws_val) == str:
            ws_val = ws_val.strip()
        mdb_val = getattr(mdb_row, ws_key, None)
        if type(mdb_val) == str:
            mdb_val = mdb_val.strip()
        if (mdb_val is None or mdb_val == '') and (ws_val is None or ws_val == ''):
            continue    # None and '' does not require updating
        if ws_key == 'EXPIRY':
            if not ws_val:
                continue    # Nothing new in the xlsx, so don't overwrite the old value.
            if mdb_val and mdb_val < _dt_low and ws_val and ws_val < _dt_low:
                continue
            if mdb_val and mdb_val > _dt_high and ws_val and ws_val > _dt_high:
                continue
        if ws_key == 'Email' and ws_val == '':
            continue    # Nothing new in the xlsx, so don't overwrite the old value.
        if mdb_val != ws_val:
            # print(f'For {ws_row["NUMBER"]}, {ws_key}: "{mdb_val}" != "{ws_val}"')
            unequal_cols.append(ws_key)
    return unequal_cols


def _province_to_pp(province):
    # This method handles variations in long names
    p = (province or '').upper()
    return None if province is None \
        else '' if type(province) != str \
        else 'AB' if 'ALB' in p \
        else 'BC' if 'BRI' in p \
        else 'MB' if 'MAN' in p \
        else 'NB' if 'BRU' in p \
        else 'NL' if 'FOU' in p \
        else 'NT' if 'WES' in p \
        else 'NS' if 'SCO' in p \
        else 'NU' if 'NUN' in p \
        else 'ON' if 'ONT' in p \
        else 'PE' if 'PRI' in p \
        else 'QC' if 'QU' in p \
        else 'SK' if 'SAS' in p \
        else 'YT' if 'YUK' in p \
        else 'US' if 'US' in p \
        else 'FO' if 'FO' in p \
        else province


class XLSX:
    def __init__(self, filename, sheetname):
        self.filename = filename
        self.sheetname = sheetname

    def get_all(self):
        wb = openpyxl.load_workbook(
            filename=self.filename,
            data_only=True, read_only=True
        )
        ws = wb[self.sheetname]
        keys = []
        is_first_row = True
        for row in ws.rows:
            if is_first_row:
                keys = [c.value for c in row]
                is_first_row = False
            else:
                vals = [c.value for c in row]
                if len(vals) < len(keys):
                    vals += (len(keys) - len(vals)) * ['']
                data = dict(zip(keys, vals))
                yield data


class MDB:
    def __init__(self, filename, password, table, key):
        self.filename = filename
        self.password = password
        self.table = table
        self.key = key
        self.dbconn = None

    # def get_all(self):
    #     pass

    def get_id(self, id):
        id = float(id)
        dbcsr = self._get_dbconn().cursor()
        sql = f'select * from "{self.table}" where "{self.key}" = ?'
        dbcsr.execute(sql, id)
        row = dbcsr.fetchone()
        dbcsr.close()
        return row

    def insert_id(self, id, row):
        id = float(id)
        dbcsr = self._get_dbconn().cursor()
        sql_settings = 'set "COL1"=?, "COL2"=?'
        sql = f'insert into "{self.table}" (col1, col2, col3) values (?, ?, ?)'
        dbcsr.close()


    def update_id(self, id, row, map):
        id = float(id)
        dbcsr = self._get_dbconn().cursor()
        sql_settings = 'set "COL1"=?, "COL2"=?'
        sql = f'update "{self.table}" set {sql_settings} where "{self.key}"=?'
        dbcsr.close()

    def _get_dbconn(self):
        if self.dbconn is None:
            pyodbc.pooling = False
            driver = '{Microsoft Access Driver (*.mdb)}'
            dbdsn = f'DRIVER={driver};DBQ={self.filename};'    # error if DBQ has quotes
            if self.password:
                dbdsn += f'PWD={self.password};'
            self.dbconn = pyodbc.connect(dbdsn)
        return self.dbconn



# ----------------------------------------------------------------------
# Notes:
#   - Ref: https://github.com/mkleehammer/pyodbc/wiki/Tips-and-Tricks-by-Database-Platform
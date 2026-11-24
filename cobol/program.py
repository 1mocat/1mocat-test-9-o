"""Port of BOOKFORUM, using the original fixed-width sequential files."""

import os
import sys
from pathlib import Path


class SequentialFile:
    """A COBOL file descriptor retains its record buffer and length on reopen."""

    def __init__(self, path, width):
        self.path = path
        self.width = self.read_size = width
        self.buffer = bytearray(width)

    def read(self, file):
        chunk = file.read(self.read_size)
        if not chunk:
            return False
        self.read_size = len(chunk)
        self.buffer[:self.read_size] = chunk
        return True

    def rewrite(self, file, record):
        if self.read_size != self.width:
            raise FileStatus(self.path, 44, "record overflow")
        file.seek(-self.width, os.SEEK_CUR)
        file.write(record)


class FileStatus(Exception):
    def __init__(self, path, code, message):
        super().__init__(f"{message} (status = {code}) for {path}")


def display_number(field):
    """Interpret PIC 9 DISPLAY data the way GnuCOBOL arithmetic does."""
    if field[0] == 0:
        return -(10 ** len(field))
    if field[0] == 255:
        return 10 ** len(field)
    value = 0
    for byte in field:
        value = value * 10 + (byte & 0x0F)
    return value


def balance_field(value):
    # The unsigned ten-digit field drops the sign and any high-order digits.
    return f"{abs(value) % 10**10:010d}".encode("ascii")


def main(root=Path(__file__).resolve().parent):
    with (root / "src/INPUT.DAT").open("rb") as source:
        request = source.read(22)
    if not request:
        print("Error: Input file is empty")
        return

    request = request.ljust(22, b"\0")
    buyer, seller, book = request[:4], request[4:8], request[8:12]
    # The numeric MOVE replaces spaces and low values with display zero.
    amount_field = request[12:].replace(b" ", b"0").replace(b"\0", b"0")
    # WS-AMOUNT has two implied decimal places, both zero after this MOVE.
    amount = display_number(amount_field + b"00") // 100

    data = root / "data"
    accounts = SequentialFile(data / "ACCOUNTS.DAT", 34)
    books = SequentialFile(data / "BOOKS.DAT", 28)

    buyer_found = seller_found = False
    with accounts.path.open("rb") as file:
        while accounts.read(file):
            account_id = accounts.buffer[:4]
            buyer_found |= account_id == buyer
            seller_found |= account_id == seller

    valid_owner = False
    with books.path.open("rb") as file:
        while books.read(file):
            row = books.buffer
            valid_owner |= row[:4] == book and row[24:28] == seller

    print(" ")
    if not (buyer_found and seller_found and valid_owner):
        print("Transaction failed due to validation errors")
        return

    with accounts.path.open("r+b") as file:
        while accounts.read(file):
            row = accounts.buffer
            account_id = row[:4]
            if account_id == buyer:
                balance = display_number(row[24:34]) - amount
                accounts.rewrite(file, row[:24] + balance_field(balance))
                if account_id == seller:
                    # COBOL attempts a second REWRITE without an intervening READ.
                    raise FileStatus(accounts.path, 43, "READ must be executed first")
            elif account_id == seller:
                balance = display_number(row[24:34]) + amount
                accounts.rewrite(file, row[:24] + balance_field(balance))

    with books.path.open("r+b") as file:
        while books.read(file):
            row = books.buffer
            if row[:4] == book:
                books.rewrite(file, row[:24] + buyer)

    # OPEN EXTEND on this non-optional file requires the file to exist.
    with (data / "TRANSACTIONS.DAT").open("r+b") as file:
        file.seek(0, os.SEEK_END)
        file.write(book + amount_field + seller + buyer)
    print("Transaction completed successfully")


if __name__ == "__main__":
    try:
        main()
    except (FileStatus, OSError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)

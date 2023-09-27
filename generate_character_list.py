"""
Download the latest unicode tables from  https://www.unicode.org and create a .txt file
containing all the names, blocks and character codes
"""
import sys
import os
import logging
from urllib import request

curr_path = os.path.dirname(__file__)
logging.basicConfig(level=logging.DEBUG)

# Be compatible with both python 2 and 3
if sys.version_info[0] >= 3:
    unichr = chr

BASE_URL = "https://www.unicode.org/Public/UCD/latest/ucd"

def get_blocks():
    """ Download the info file for Unicode blocks.
    """
    logging.info("Downloading block data...")
    with request.urlopen(f"{BASE_URL}/Blocks.txt") as req:
        content = req.read().decode()
    logging.info("Done")
    return content


def get_data():
    """ Download the info file for Unicode blocks.
    """
    logging.info("Downloading character data...")
    with request.urlopen(f"{BASE_URL}/UnicodeData.txt") as req:
        content = req.read().decode()
    logging.info("Done")
    return content


def clean(text):
    """ Remove all blank or commented lies from a string
    """
    lines = text.strip().split("\n")
    clean_lines = [line.strip() for line in lines if line.strip() and line[0] != "#"]
    return "\n".join(clean_lines)


def load_blocks():
    """ Load and parse the block data and return a function that provides block
    search based on a character code.
    """
    indices = []
    blocks = []
    block_data = clean(get_blocks())
    for line in block_data.split("\n"):
        l, name = line.split(";")
        start, stop = l.split("..")
        indices.append((int(start, 16), int(stop, 16)))
        blocks.append(name.strip())

    def locate_block(code, left=0, right=len(indices)):
        """
        Binary search on an ordered list of intervals.
        """
        half = left + (right - left) // 2
        [start, end] = indices[half]
        if start > code:
            return locate_block(code, left, right=half)
        if end < code:
            return locate_block(code, half, right=right)
        return blocks[half]

    return locate_block


def main(out: str = "unicode_list.txt"):
    """Create the file with Unicode characters.

    Read the character and block data and unite them to a text file
    containing the following fields, separated by tab characters:
    `<character name> <character comment> <code> <block name>`
    """
    get_block = load_blocks()
    characters = clean(get_data())

    logging.info("Parsing character data...")
    output = []
    for line in characters.split("\n"):
        # Parse the needed data from the character's line
        attributes = line.strip().split(";")
        code = attributes[0]
        name = attributes[1]
        comment = attributes[10]

        # Convert character code to unicode
        try:
            num = int(code, 16)
        except ValueError:
            logging.warning("Could not convert %s", code)
            continue

        # Find the character's block
        blk = get_block(num)
        if blk is not None:
            output.append("\t".join((name, comment, code, blk)))
        else:
            logging.warning("Code %s not found in any block, char: %s", num, unichr(num))
            output.append(name + "\t" + comment + "\t" + code + "\t")

    with open(out, "w", encoding="utf-8") as target:
        target.write("\n".join(output))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        type=str,
        help="the output path where to save the Unicode list.",
        default="unicode_list.txt",
    )

    args = parser.parse_args()

    main(args.path)

import os
import sys
import codecs
import time
import math
import shutil
import html.entities
import asyncio
import logging
from typing import Dict, Optional
from operator import itemgetter

from ulauncher.utils.fuzzy_search import get_score
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction

logger = logging.getLogger(__name__)

# Be compatible with both python 2 and 3
if sys.version_info[0] >= 3:
    unichr = chr

FILE_PATH = os.path.dirname(sys.argv[0])

ICON_TEMPLATE = """
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="50" fill="white" />
  <text x="50" y="50" dy=".35em" text-anchor="middle" font-family="{font}" font-size="60">{symbol}</text>
</svg>
"""

ExtensionPreferences = Dict[str, str]
UnicodeCharPreferences = Dict[str, int]


class UnicodeChar:
    """Container class for unicode characters."""

    def __init__(self, name, comment, block, code):
        self.name = name if name != "<control>" else comment
        self.comment = comment
        self.block = block
        self.code = code
        self.character = unichr(int(code, 16))

    def get_search_name(self):
        """Called to get the string that should be used in searches."""
        return " ".join([self.character, self.code, self.name, self.comment])


class UnicodeCharExtension(Extension):
    unicode_path: str = "unicode_list.txt"

    def __init__(self):
        super().__init__()
        check_cache_dir()
        self._load_character_table()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

    def get_filename(self) -> str:
        """Default filename of the Unicode list."""
        return os.path.join(FILE_PATH, self.unicode_path)

    def _load_character_table(self):
        """Read the data file and load to memory."""
        filename = self.get_filename()

        self.character_list = []
        with open(filename, "r", encoding="utf-8") as f:
            for line in f.readlines():
                name, comment, code, block = line.strip().split("\t")
                character = UnicodeChar(name, comment, block, code)
                self.character_list.append(character)

    @staticmethod
    async def refresh_unicode_list(path: str, preferences: UnicodeCharPreferences):
        """Check if the Unicode list file needs refresh."""
        # Get timestamp of the last time the file was modified
        timestamp = os.path.getmtime(path)
        # Number of days since the file was modified
        age = math.floor((time.time() - timestamp) / 3600)

        update_interval = preferences["update_interval"]

        if 0 < update_interval < age:
            await UnicodeCharExtension.update_unicode_list(path)

    @staticmethod
    async def update_unicode_list(path: str):
        """Re-generate an old Unicode list file."""
        # Save the file to a backup file if there is no backup.
        backup = path + ".bkp"
        if not os.path.isfile(backup):
            logger.info("backup the file with Unicode list to: %s", backup)
            shutil.copyfile(path, backup)

        import generate_character_list

        # Regenerate file with unicode list
        logger.info("regenerate the file with Unicode list: %s", path)
        generate_character_list.main(path)

    @staticmethod
    def get_preferences(
        input_preferences: ExtensionPreferences,
    ) -> UnicodeCharPreferences:
        """Parse preferences to the correct types."""
        preferences: UnicodeCharPreferences = {
            "result_limit": int(input_preferences["result_limit"]),
            "min_score": int(input_preferences["min_score"]),
            "update_interval": int(input_preferences["update_interval"]),
        }

        return preferences

    def search(self, query: str, preferences: UnicodeCharPreferences):
        """Return a list of result sorted by relevance to the query."""
        limit = preferences["result_limit"]
        min_score = preferences["min_score"]

        results = []
        for c in self.character_list:
            score = get_score(query, c.get_search_name())
            if score >= min_score:
                results.append((score, c))
                results = sorted(results, reverse=True, key=itemgetter(0))
                if len(results) > limit:
                    results = results[:limit]

        return [c for (s, c) in results]


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        preferences = extension.get_preferences(extension.preferences)
        # Re-generate unicode list if it is too old.
        coro = extension.refresh_unicode_list(extension.get_filename(), preferences)
        # start the event loop and execute the coroutine
        asyncio.run(coro)

        items = []
        query = event.get_argument().strip()
        if query:
            # Return best characters matching the query, ordered by score.
            results = extension.search(query, preferences)
            for char in results:
                image_path = get_character_icon(char)
                html_val = html_encode(char.character)
                html_str = ""
                if html_val:
                    html_str = f" - HTML: {html_val}"

                items.append(
                    ExtensionResultItem(
                        icon=image_path,
                        name=f"{char.name.capitalize()} - {char.character}",
                        description=f"{char.block}{html_str} - Alt+Enter: U+{char.code}",
                        on_enter=CopyToClipboardAction(char.character),
                        on_alt_enter=CopyToClipboardAction(char.code),
                    )
                )
        return RenderResultListAction(items)


def html_encode(char: str) -> Optional[str]:
    """Get the html encoded str corresponding to the unicode char, if it exist."""
    if ord(char) in html.entities.codepoint2name:
        html_var = html.entities.codepoint2name[ord(char)]
        return f"&{html_var};"
    return None


def get_character_icon(char):
    """Check if there is an existing icon for this character and return its path
    or create a new one and return its path.
    """
    path = os.path.join(FILE_PATH, f"images/cache/icon_{char.code}.svg")
    if os.path.isfile(path):
        return path
    return create_character_icon(char)


def create_character_icon(char, font="sans-serif"):
    """Create an SVG file containing the unicode glyph for char to be used
    as a result icon.

    Note: this could be avoided by providing a gtk.PixBuf without creating a file,
    but ulauncher pickles the returned results, so it doesn't work currently.
    """
    icon = ICON_TEMPLATE.format(symbol=char.character, font=font)
    path = os.path.join(FILE_PATH, f"images/cache/icon_{char.code}.svg")
    with codecs.open(path, "w", "utf-8") as target:
        target.write(icon)
    return path


def check_cache_dir(path="images/cache"):
    """Check if the cache directory exists and if not create it."""
    path = os.path.join(FILE_PATH, path)
    if not os.path.isdir(path):
        os.mkdir(path)


if __name__ == "__main__":
    UnicodeCharExtension().run()

from typing import List, Optional

import requests
from lxml import etree

from static.color import Color
from unit.handle_log import setup_logging


logger = setup_logging(
    'pssh', 'aquamarine'
)


def extract_pssh(response: requests.Response) -> List[str]:
    try:
        namespaces = {"cenc": "urn:mpeg:cenc:2013", "mspr": "urn:microsoft:playready"}
        root = etree.fromstring(response.content)

        pssh_elements = root.xpath("//cenc:pssh", namespaces=namespaces)

        return [pssh.text.strip() for pssh in pssh_elements if pssh.text]

    except etree.XMLSyntaxError as e:
        logger.error(f"XML parsing error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error during PSSH extraction: {e}")
        return []


class GetMPD_wv:
    def parse_pssh(raw_mpd):

        pssh_values = extract_pssh(raw_mpd)

        if not pssh_values:
            logger.warning(f"{Color.bg('mint')}No WV PSSH values found in the MPD file.{Color.reset()}")
            return None

        for pssh in pssh_values:
            if len(pssh) == 76:
                return pssh

        logger.error("No WV PSSH value with exactly 76 characters found")
        return None
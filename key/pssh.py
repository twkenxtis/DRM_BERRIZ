from typing import List, Optional, Dict

import requests
from lxml import etree
from lxml.etree import _Element

from static.color import Color
from unit.handle.handle_log import setup_logging


logger = setup_logging(
    'pssh', 'aquamarine'
)


def extract_pssh(response: requests.Response) -> List[str]:
    """
    從 MPD XML 中提取 cenc:pssh 元素的文字內容

    :param response: XML 字串或 bytes
    :return: PSSH 字串列表
    """
    try:
        # 如果是 requests.Response，先取出 text 或 content
        if hasattr(response, "text"):
            xml_data = response.text
        elif hasattr(response, "content"):
            xml_data = response.content
        else:
            xml_data = response  # 已是 str 或 bytes

        # 確保是 bytes，避免 encoding 問題
        if isinstance(xml_data, str):
            xml_data = xml_data.encode("utf-8")

        # 解析 XML
        root = etree.fromstring(xml_data)

        namespaces: Dict[str, str] = {"cenc": "urn:mpeg:cenc:2013", "mspr": "urn:microsoft:playready"}

        pssh_elements = root.xpath("//cenc:pssh", namespaces=namespaces)
        return [pssh.text.strip() for pssh in pssh_elements if pssh.text]

    except etree.XMLSyntaxError as e:
        logger.error(f"XML parsing error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error during PSSH extraction: {e}")
        return []


class GetMPD_wv:
    @staticmethod
    def parse_pssh(raw_mpd: requests.Response) -> Optional[List[str]]:
        """
        解析 MPD 檔案的回應，提取 PSSH 值，並過濾出長度為 76 的有效值
        """
        # extract_pssh 返回 List[str]
        pssh_values: List[str] = extract_pssh(raw_mpd)
        if not pssh_values:
            logger.warning(f"{Color.bg('mint')}No WV PSSH values found in the MPD file.{Color.reset()}")
            return None

        valid_pssh_list: List[str] = []
        for pssh in pssh_values:
            if len(pssh) == 76:
                valid_pssh_list.append(pssh)

        if valid_pssh_list:
            return valid_pssh_list
        else:
            logger.error("No MSPR:PRO PSSH value with exactly 76 characters found")
            return None
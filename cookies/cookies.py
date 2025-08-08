import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import requests


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class Refresh_JWT:
    INITIAL_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": "https://berriz.in/",
        "Origin": "https://berriz.in",
        "Alt-Used": "account.berriz.in",
        "Connection": "keep-alive",
        "bz_r": (
            "BbC1Fovqbj6lRVFZqaDZN07MBkNZQddEUfBFTOBn8BxQvhS4anDhA7WmiAsACOMo5Xl9jjv447lUvLufcV"
        ),
        "TE": "trailers",
    }

    REFRESH_FILE = Path(r"cookies\\refresh_time.txt")

    if not os.path.exists("cookies"):
        os.mkdir("cookies")

    @classmethod
    def get_bz_r(cls):
        return cls.INITIAL_HEADERS["bz_r"]

    def refresh_token(current_access_token=None):
        url = "https://account.berriz.in/auth/v1/token:refresh?languageCode=en"
        headers = Refresh_JWT.INITIAL_HEADERS.copy()
        json_data = {"clientId": "e8faf56c-575a-42d2-933d-7b2e279ad827"}

        try:
            response = requests.post(url, headers=headers, json=json_data)
            logging.info(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - {response.status_code} {url}"
            )

            if response.status_code == 200:
                json_obj = response.json()
                access_token = json_obj["data"]["accessToken"]

                try:
                    decoded_token = jwt.decode(
                        access_token, options={"verify_signature": False}
                    )
                    exp_time = decoded_token["exp"]
                    readable_time = datetime.fromtimestamp(exp_time).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    logging.info(f"Token will expire at {readable_time}")
                except Exception as decode_error:
                    logging.warning(f"Failed to decode token: {decode_error}")

                with open(r"cookies\\bz_a.txt", "w") as f:
                    f.write(access_token)

                logging.info(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - Access Token saved to bz_a.txt"
                )
                return access_token
            else:
                logging.error(f"FAILED: {response.text}")
                return None
        except Exception as e:
            logging.error(f"ERROR: {e}")
            return None

    def my_state_test():
        with open(r"cookies\\bz_a.txt", "r") as f:
            bz_a = f.read().strip()

        cookies = {
            "pcid": "AB0FABCB-9CE5-4D0A-B7C2-A5DD30BA3B8E",
            "pacode": "fanplatf::app:ios:phone:",
            "_T_ANO": (
                "FoRDIrCzeSl6AF0d6ezaH2mG0UgBZnABPj+H1cMxfkzdnsIep49V0mp7329rZdBuNKzxFIJAj9a3"
                "UbIHrT8kAAlaUUb4aiPCd1JCINiZOWeHImyO3JyTWCU8e72VElffdZtlVoDrTAx/CErQitGFCZpxc"
                "gaOwPh7R5/rXTKv7RC46dtQ6axR/optyRzSdXYKPllc4r6RGGEq90E9Nllgp0nMaHqhUAJ6bB9+qL7"
                "9UQrHl76cAamttMSsfPQcxfddTd7ab8DHZuZAyCn7uSdWf01Tm5Y93lW2OD5RyvWr/9K7ihapcJX03m"
                "Z0Qw8xqW1dOLx1AWOS5BrHUml8d0utvg=="
            ),
            "__T_": "1",
            "__T_SECURE": "1",
            "bz_a": f"{bz_a}; ",
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; "
                "iPhone17.6.1; fanz-ios 1.1.4; iPhone12,3"
            ),
            "Accept": "application/json",
            "Referer": "https://berriz.in/",
            "Alt-Used": "svc-api.berriz.in",
            "Connection": "keep-alive",
        }

        params = {"languageCode": "en"}

        response = requests.get(
            "https://svc-api.berriz.in/service/v1/my/state",
            params=params,
            cookies=cookies,
            headers=headers,
        )
        response_json = response.json()
        if response_json.get("message") == "SUCCESS":
            logging.info("Cookie test successful.")
        else:
            logging.error("Cookie test failed.")

    def refresh_and_test():
        token = Refresh_JWT.refresh_token()
        if not token:
            logging.error("Initial token refresh failed.")
            return None
        time.sleep(1)
        Refresh_JWT.my_state_test()
        return token

    def should_refresh() -> bool:
        if not Refresh_JWT.REFRESH_FILE.exists():
            return True

        try:
            with open(Refresh_JWT.REFRESH_FILE, "r") as f:
                timestamp_str = f.read().strip()
                next_refresh_time = datetime.strptime(
                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                )
                now = datetime.now()
                delta = (next_refresh_time - now).total_seconds()
                """
                logging.info(
                    f"Next scheduled refresh time: {next_refresh_time} (in {int(delta)} sec)"
                )
                """
                return delta < 60
        except Exception as e:
            logging.warning(f"Failed to parse refresh_time.txt: {e}")
            return True

    def write_next_refresh_time():
        next_time = datetime.now() + timedelta(minutes=50)
        with open(Refresh_JWT.REFRESH_FILE, "w") as f:
            f.write(next_time.strftime("%Y-%m-%d %H:%M:%S"))
        logging.info(
            f"Next refresh time written to {Refresh_JWT.REFRESH_FILE}: {next_time}"
        )

    def main():
        if Refresh_JWT.should_refresh():
            logging.info("Token refresh triggered.")
            token = Refresh_JWT.refresh_and_test()
            if token:
                Refresh_JWT.write_next_refresh_time()
            else:
                logging.warning("Refresh failed, next refresh time not updated.")
        else:
            # logging.info("No need to refresh token yet.")
            pass


class Berriz_cookie:
    def __init__(self):
        self._cookies = {}
        self.load_cookies()

    def load_cookies(self) -> None:
        file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), r"bz_a.txt"
        )
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                pass
        with open(file_path, "r", encoding="utf-8") as f:
            bz_a = f.read().strip()

        self._cookies = {
            "_T_ANO": (
                "FoRDIrCzeSl6AF0d6ezaH2mG0UgBZnABPj+H1cMxfkzdnsIep49V0mp7329rZdBuNKzxFIJAj9a3"
                "UbIHrT8kAAlaUUb4aiPCd1JCINiZOWeHImyO3JyTWCU8e72VElffdZtlVoDrTAx/CErQitGFCZpxc"
                "gaOwPh7R5/rXTKv7RC46dtQ6axR/optyRzSdXYKPllc4r6RGGEq90E9Nllgp0nMaHqhUAJ6bB9+qL7"
                "9UQrHl76cAamttMSsfPQcxfddTd7ab8DHZuZAyCn7uSdWf01Tm5Y93lW2OD5RyvWr/9K7ihapcJX03m"
                "Z0Qw8xqW1dOLx1AWOS5BrHUml8d0utvg=="
            ),
            "pacode": "fanplatf::app:ios:phone:",
            "pcid": "AB0FABCB-9CE5-4D0A-B7C2-A5DD30BA3B8E",
            "__T_": "1",
            "__T_SECURE": "1",
            "bz_a": f"{bz_a}",
            "bz_r": f"{Refresh_JWT.get_bz_r()}",
        }

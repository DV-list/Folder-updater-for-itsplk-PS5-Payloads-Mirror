"""Remote payloads.json retrieval and validation."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import PayloadEntry


class PayloadCatalogError(Exception):
    """Raised when the remote catalog cannot be retrieved or validated."""


class PayloadCatalog:
    """Retrieve the remote catalog and expose fields used by the application."""

    TIMEOUT_SECONDS = 15
    USER_AGENT = "Folder-updater/1.9.7"

    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> list[PayloadEntry]:
        """Fetch payloads.json and validate the required fields."""
        # Use HTTPS and an explicit timeout. The caller treats retrieval failures as
        # SERVER UNAVAILABLE rather than as an unknown local checksum.
        if not self.url.lower().startswith("https://"):
            raise PayloadCatalogError("payloads.json URL must use HTTPS")

        request = Request(
            self.url,
            headers={"User-Agent": self.USER_AGENT},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise PayloadCatalogError(
                        f"HTTP {response.status} while fetching payloads.json"
                    )
                raw = response.read()
        except HTTPError as exc:
            raise PayloadCatalogError(
                f"HTTP {exc.code} while fetching payloads.json"
            ) from exc
        except URLError as exc:
            raise PayloadCatalogError(
                f"Network error while fetching payloads.json: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise PayloadCatalogError(
                f"Unable to fetch payloads.json: {exc}"
            ) from exc

        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PayloadCatalogError(
                "payloads.json is not valid UTF-8 JSON"
            ) from exc

        # The catalog now wraps its entries in a top-level object containing
        # metadata and a "payloads" array. Keep legacy array compatibility.
        if isinstance(document, dict):
            document = document.get("payloads")
            if not isinstance(document, list):
                raise PayloadCatalogError(
                    "payloads.json object must contain a 'payloads' array"
                )
        elif not isinstance(document, list):
            raise PayloadCatalogError(
                "payloads.json root must be an array or an object containing a 'payloads' array"
            )

        entries: list[PayloadEntry] = []

        # Keep the server filename because the updater must use the catalog's
        # authoritative target filename rather than deriving it from local names.
        for index, item in enumerate(document):
            if not isinstance(item, dict):
                raise PayloadCatalogError(
                    f"payloads.json entry {index} is not an object"
                )

            name = item.get("name")
            filename = item.get("filename")
            version = item.get("version")
            checksum = item.get("checksum")
            source_direct = item.get("source_direct")
            extract_file = item.get("extract_file")

            if not all(
                isinstance(value, str) and value
                for value in (name, filename, version, checksum)
            ):
                raise PayloadCatalogError(
                    f"payloads.json entry {index} is missing required name/filename/version/checksum"
                )

            if source_direct is not None and not isinstance(source_direct, str):
                source_direct = None
            if extract_file is not None and not isinstance(extract_file, str):
                extract_file = None

            entries.append(
                PayloadEntry(
                    payload=name,
                    filename=filename,
                    version=version,
                    checksum=checksum.lower(),
                    source_direct=source_direct,
                    extract_file=extract_file,
                )
            )

        return entries

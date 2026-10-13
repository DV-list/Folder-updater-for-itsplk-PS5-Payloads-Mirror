"""Remote payloads.json retrieval and validation."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.models import PayloadEntry


class PayloadCatalogError(Exception):
    """Raised when the remote catalog cannot be retrieved or validated."""


class PayloadCatalog:
    """Retrieve the remote catalog and expose fields used by the application."""

    TIMEOUT_SECONDS = 15
    USER_AGENT = "Folder-updater/1.9.9"

    def __init__(self, url: str) -> None:
        self.url = url
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _safe_url(url: str) -> str:
        """Return an HTTP URL without query parameters or fragments."""
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

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

        self.logger.debug("HTTP request starting: GET %s", self._safe_url(self.url))
        try:
            with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                self.logger.debug(
                    "HTTP response: status=%s content_type=%s content_length=%s url=%s",
                    response.status,
                    response.headers.get("Content-Type"),
                    response.headers.get("Content-Length"),
                    self._safe_url(self.url),
                )
                if response.status != 200:
                    raise PayloadCatalogError(
                        f"HTTP {response.status} while fetching payloads.json"
                    )
                raw = response.read()
                self.logger.debug("HTTP body received: %s bytes from %s", len(raw), self._safe_url(self.url))
        except HTTPError as exc:
            self.logger.warning("HTTP request failed: status=%s url=%s", exc.code, self._safe_url(self.url))
            raise PayloadCatalogError(
                f"HTTP {exc.code} while fetching payloads.json"
            ) from exc
        except URLError as exc:
            self.logger.warning("HTTP transport failed for %s: %s", self._safe_url(self.url), exc.reason)
            raise PayloadCatalogError(
                f"Network error while fetching payloads.json: {exc.reason}"
            ) from exc
        except OSError as exc:
            self.logger.warning("HTTP I/O failed for %s: %s", self._safe_url(self.url), exc)
            raise PayloadCatalogError(
                f"Unable to fetch payloads.json: {exc}"
            ) from exc

        self.logger.debug("Catalog parsing started: decoding UTF-8 JSON (%s bytes)", len(raw))
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.logger.warning("Catalog parsing failed: response is not valid UTF-8 JSON")
            raise PayloadCatalogError(
                "payloads.json is not valid UTF-8 JSON"
            ) from exc

        self.logger.debug("Catalog JSON parsed; root type=%s", type(document).__name__)
        # The catalog now wraps its entries in a top-level object containing
        # metadata and a "payloads" array. Keep legacy array compatibility.
        if isinstance(document, dict):
            self.logger.debug("Catalog wrapper keys: %s", sorted(document.keys()))
            document = document.get("payloads")
            if not isinstance(document, list):
                self.logger.warning("Catalog wrapper is missing a valid payloads array")
                raise PayloadCatalogError(
                    "payloads.json object must contain a 'payloads' array"
                )
        elif not isinstance(document, list):
            self.logger.warning("Catalog root has unsupported type: %s", type(document).__name__)
            raise PayloadCatalogError(
                "payloads.json root must be an array or an object containing a 'payloads' array"
            )

        self.logger.debug("Catalog payload array validated: %s entries", len(document))
        entries: list[PayloadEntry] = []

        # Keep the server filename because the updater must use the catalog's
        # authoritative target filename rather than deriving it from local names.
        for index, item in enumerate(document):
            if not isinstance(item, dict):
                self.logger.warning("Catalog entry %s has unsupported type: %s", index, type(item).__name__)
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
                self.logger.warning("Catalog entry %s is missing required fields", index)
                raise PayloadCatalogError(
                    f"payloads.json entry {index} is missing required name/filename/version/checksum"
                )

            if source_direct is not None and not isinstance(source_direct, str):
                source_direct = None
            if extract_file is not None and not isinstance(extract_file, str):
                extract_file = None

            self.logger.debug(
                "Parsed catalog entry %s: payload=%s filename=%s version=%s checksum=%s",
                index,
                name,
                filename,
                version,
                checksum.lower(),
            )
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

        self.logger.debug("Catalog parsing completed successfully: %s entries", len(entries))
        return entries

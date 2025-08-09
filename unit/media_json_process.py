from typing import List, Dict, Any


class MediaJsonProcessor:
    """A class for processing JSON media data and extracting relevant information."""

    @staticmethod
    def process_selection(
        selected_media: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Process the selected media dictionary and return categorized media items."""
        processed = {"vods": [], "photos": []}

        # Process VODs
        if "vods" in selected_media and selected_media["vods"]:
            processed["vods"] = [
                item
                for item in selected_media["vods"]
                if "mediaId" in item and "mediaType" in item
            ]

        # Process Photos
        if "photos" in selected_media and selected_media["photos"]:
            processed["photos"] = [
                item
                for item in selected_media["photos"]
                if "mediaId" in item and "mediaType" in item
            ]

        return processed
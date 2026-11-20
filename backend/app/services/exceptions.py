class CampaignServiceError(Exception):
    """Ошибка одного из шагов создания кампании."""

    def __init__(
        self,
        step: str,
        error: str,
        campaign_id: int | None = None,
    ) -> None:
        super().__init__(error)
        self.step = step
        self.error = error
        self.campaign_id = campaign_id


class ValidationError(CampaignServiceError):
    def __init__(self, error: str) -> None:
        super().__init__(step="validation", error=error)


class CampaignStepError(CampaignServiceError):
    def __init__(self, error: str, campaign_id: int | None = None) -> None:
        super().__init__(step="campaign", error=error, campaign_id=campaign_id)


class StreamGoogleError(CampaignServiceError):
    def __init__(self, error: str, campaign_id: int) -> None:
        super().__init__(
            step="stream_google", error=error, campaign_id=campaign_id
        )


class StreamOfferError(CampaignServiceError):
    def __init__(self, error: str, campaign_id: int) -> None:
        super().__init__(
            step="stream_offer", error=error, campaign_id=campaign_id
        )


class DbError(CampaignServiceError):
    def __init__(self, error: str, campaign_id: int) -> None:
        super().__init__(step="db", error=error, campaign_id=campaign_id)


class NotFoundError(CampaignServiceError):
    def __init__(self, error: str) -> None:
        super().__init__(step="not_found", error=error)

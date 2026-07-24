from nitro_common.config import BaseNitroSettings


class Settings(BaseNitroSettings):
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    auth_password: str = ""
    auth_secret_key: str = "nitro-dev-secret-change-in-production"
    auth_cookie_secure: bool = True

    watchlist_csv_path: str = "/shared/watchlist/netlist-latest.csv"
    k8s_namespace: str = "nitro"
    k8s_job_image: str = "gcr.io/nitro-wagering/paper-monitor:latest"

    service_timeout: int = 30


settings = Settings()

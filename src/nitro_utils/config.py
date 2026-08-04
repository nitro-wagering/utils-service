from nitro_common.config import BaseNitroSettings


class Settings(BaseNitroSettings):
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    auth_password: str = ""
    auth_secret_key: str = "nitro-dev-secret-change-in-production"
    auth_cookie_secure: bool = True

    k8s_namespace: str = "nitro"
    k8s_job_image: str = "gcr.io/nitro-wagering/paper-monitor:latest"

    service_timeout: int = 30

    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30

    s3_endpoint_url: str = "https://s3.awgmi.dev"
    s3_access_key: str = ""  # From NITRO_S3_ACCESS_KEY
    s3_secret_key: str = ""  # From NITRO_S3_SECRET_KEY
    s3_bucket: str = "nitro"


settings = Settings()

from app.config import get_settings


def configure_telemetry() -> None:
    connection_string = get_settings().applicationinsights_connection_string
    if not connection_string:
        return
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(
        connection_string=connection_string,
        enable_live_metrics=False,
    )

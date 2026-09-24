import json
import uuid

import click

from intelgraph.core.source.connector import ConnectorConfig, ConnectorRegistry
from intelgraph.core.source.store import DataSourceStore


@click.group(name="datasources", help="Manage data sources and connectors")
def datasource_group() -> None:
    pass


def _get_store(ctx: click.Context) -> DataSourceStore:
    cfg = ctx.obj["config"]
    db_path = cfg.get("storage", {}).get("path", "intelgraph.db")
    store = DataSourceStore(db_path)
    store.connect()
    return store


@datasource_group.command(name="register", help="Register a new data source")
@click.option("--name", required=True, help="Data source name")
@click.option(
    "--type",
    "connector_type",
    required=True,
    type=click.Choice(["http", "file", "database"], case_sensitive=False),
    help="Connector type",
)
@click.option("--endpoint", default=None, help="HTTP endpoint URL (for http type)")
@click.option("--file-path", default=None, help="File path (for file type)")
@click.option("--conn-string", default=None, help="Database connection string (for database type)")
@click.option("--query", default=None, help="SQL query (for database type)")
@click.option("--poll-interval", type=int, default=3600, help="Polling interval in seconds")
@click.option("--auth-type", default=None, help="Authentication type (api_key, basic)")
@click.option("--api-key", default=None, help="API key (for api_key auth)")
@click.option("--retry", type=int, default=3, help="Max retry attempts")
@click.option("--schema", default=None, help="Feed schema JSON file path")
@click.option("--enabled/--disabled", default=True, help="Enable the data source")
@click.pass_context
def register(
    ctx: click.Context,
    name: str,
    connector_type: str,
    endpoint: str | None,
    file_path: str | None,
    conn_string: str | None,
    query: str | None,
    poll_interval: int,
    auth_type: str | None,
    api_key: str | None,
    retry: int,
    schema: str | None,
    enabled: bool,
) -> None:
    store = _get_store(ctx)
    feed_schema = None
    if schema:
        try:
            with open(schema) as f:
                feed_schema = json.load(f)
        except Exception as e:
            click.echo(f"Error loading schema: {e}", err=True)
            raise click.Abort()

    auth_creds = {}
    if api_key:
        auth_creds["api_key"] = api_key

    cfg = ConnectorConfig(
        id=str(uuid.uuid4()),
        name=name,
        connector_type=connector_type,
        polling_interval_seconds=poll_interval,
        retry_max_attempts=retry,
        enabled=enabled,
        auth_type=auth_type,
        auth_credentials=auth_creds if auth_creds else None,
        endpoint_url=endpoint,
        file_path=file_path,
        conn_string=conn_string,
        query=query,
        feed_schema=feed_schema,
    )
    store.register_source(cfg)
    if feed_schema:
        store.save_feed_schema(cfg.id, feed_schema)
    click.echo(f"Data source registered: {name} (id: {cfg.id})")
    click.echo(f"  Type: {connector_type}")
    click.echo(f"  Endpoint: {endpoint or file_path or conn_string or 'N/A'}")
    click.echo(f"  Poll Interval: {poll_interval}s")
    click.echo(f"  Max Retries: {retry}")


@datasource_group.command(name="list", help="List registered data sources")
@click.pass_context
def list_sources(ctx: click.Context) -> None:
    store = _get_store(ctx)
    sources = store.list_sources()
    if not sources:
        click.echo("No data sources registered.")
        return
    click.echo(f"Data Sources ({len(sources)}):")
    for src in sources:
        click.echo(f"  [{src['connector_type']}] {src['name']} (id: {src['id'][:8]}...)")
        click.echo(f"    Status: {src['status']} | Enabled: {'yes' if src['enabled'] else 'no'}")
        click.echo(
            f"    Last poll: {src.get('last_poll_at', 'never')} | Status: {src.get('last_poll_status', 'N/A')}"
        )
        click.echo(f"    Failures: {src.get('consecutive_failures', 0)}")


@datasource_group.command(name="remove", help="Remove a data source")
@click.argument("source_id")
@click.pass_context
def remove(ctx: click.Context, source_id: str) -> None:
    store = _get_store(ctx)
    if store.delete_source(source_id):
        click.echo(f"Data source {source_id} removed.")
    else:
        click.echo(f"Error: Data source {source_id} not found.", err=True)
        raise click.Abort()


@datasource_group.command(name="poll", help="Poll a data source")
@click.argument("source_id")
@click.pass_context
def poll(ctx: click.Context, source_id: str) -> None:
    import time as _time

    store = _get_store(ctx)
    source = store.get_source(source_id)
    if source is None:
        click.echo(f"Error: Data source {source_id} not found.", err=True)
        raise click.Abort()

    import json as _json

    config_dict = source.get("config", {})
    if isinstance(config_dict, str):
        config_dict = _json.loads(config_dict)

    cfg = ConnectorConfig(
        id=source["id"],
        name=source["name"],
        connector_type=source["connector_type"],
        polling_interval_seconds=source.get("polling_interval_seconds", 3600),
        retry_max_attempts=source.get("retry_max_attempts", 3),
        enabled=bool(source.get("enabled", 1)),
        auth_type=config_dict.get("auth_type"),
        auth_credentials=config_dict.get("auth_credentials"),
        endpoint_url=config_dict.get("endpoint_url"),
        file_path=config_dict.get("file_path"),
        conn_string=config_dict.get("conn_string"),
        query=config_dict.get("query"),
        headers=config_dict.get("headers"),
        feed_schema=config_dict.get("feed_schema"),
        metadata=config_dict.get("metadata", {}),
    )

    connector = ConnectorRegistry.create(cfg)
    if connector is None:
        click.echo("Error: Failed to create connector.", err=True)
        raise click.Abort()

    click.echo(f"Polling {source['name']} ({source['connector_type']})...")
    if not connector.connect():
        click.echo("Error: Connection failed.", err=True)
        raise click.Abort()

    t0 = _time.perf_counter()
    result = connector.poll_with_retry()
    duration = _time.perf_counter() - t0

    if result.success:
        click.echo(f"  Success! ({round(duration * 1000, 1)}ms)")
        click.echo(f"  Records received: {len(result.raw_data)}")
        click.echo(f"  Nodes ingested: {result.nodes_ingested}")
        click.echo(f"  Edges ingested: {result.edges_ingested}")
        click.echo(f"  Duplicates removed: {result.duplicates_removed}")

        store.record_poll(
            data_source_id=source_id,
            status="success",
            duration_ms=duration * 1000,
            nodes_ingested=result.nodes_ingested,
            edges_ingested=result.edges_ingested,
            duplicates_removed=result.duplicates_removed,
        )
        store.update_source_status(source_id, "active", consecutive_failures=0)
    else:
        click.echo(f"  Failed: {result.error_message}")
        store.record_poll(
            data_source_id=source_id,
            status="failure",
            duration_ms=duration * 1000,
            error_message=result.error_message,
        )
        cf = source.get("consecutive_failures", 0) + 1
        store.update_source_status(
            source_id, "error" if cf >= 3 else "active", consecutive_failures=cf
        )

    connector.disconnect()


@datasource_group.command(name="status", help="Get data source status")
@click.argument("source_id")
@click.pass_context
def status(ctx: click.Context, source_id: str) -> None:
    store = _get_store(ctx)
    st = store.get_source_status(source_id)
    if "error" in st:
        click.echo(f"Error: Data source {source_id} not found.", err=True)
        raise click.Abort()
    click.echo(f"Status for {st['name']}:")
    click.echo(f"  ID:               {st['id']}")
    click.echo(f"  Type:             {st['connector_type']}")
    click.echo(f"  Status:           {st['status']}")
    click.echo(f"  Enabled:          {st['enabled']}")
    click.echo(f"  Consecutive Fails: {st['consecutive_failures']}")
    click.echo(f"  Last Poll:        {st['last_poll_at'] or 'never'}")
    click.echo(f"  Last Poll Status: {st['last_poll_status'] or 'N/A'}")
    click.echo(f"  Failures (24h):   {st['failures_last_24h']}")
    if st.get("latest_poll"):
        lp = st["latest_poll"]
        click.echo("  Latest Poll:")
        click.echo(f"    Status:     {lp['status']}")
        click.echo(f"    Duration:   {lp['duration_ms']}ms")
        click.echo(f"    Nodes:      {lp['nodes_ingested']}")
        click.echo(f"    Edges:      {lp['edges_ingested']}")
        click.echo(f"    Merges:     {lp['entities_merged']}")
        click.echo(f"    Dups Removed: {lp['duplicates_removed']}")

import requests
from . import constants
from dagster import asset
import duckdb
import os

@asset
def taxi_trips_file():
    """
        The raw parquet files for the taxi trips dataset. Sourced from the NYC Open Data portal.
    """
    month_to_fetch = '2023-03'
    raw_trips = requests.get(
        f"https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{month_to_fetch}.parquet"
    )

    with open(constants.TAXI_TRIPS_TEMPLATE_FILE_PATH.format(month_to_fetch), "wb") as output_file:
        output_file.write(raw_trips.content)

@asset
def taxi_zones_file():
    """
        The raw CSV file for the taxi zones dataset. Sourced from the NYC Open Data portal.
    """
    raw_taxi_zones = requests.get(
        f"https://data.cityofnewyork.us/api/views/755u-8jsi/rows.csv?accessType=DOWNLOAD"
    )

    with open(constants.TAXI_ZONES_FILE_PATH, "wb") as output_file:
        output_file.write(raw_taxi_zones.content)

@asset(
	deps=["taxi_trips_file"]
)
def taxi_trips():
		"""
        The raw taxi trips dataset, loaded into a DuckDB database
    """
		sql_query = """
				create or replace table trips as (
						select
								VendorID as vendor_id,
								PULocationID as pickup_zone_id,
								DOLocationID as dropoff_zone_id,
								RatecodeID as rate_code_id,
								payment_type as payment_type,
								tpep_dropoff_datetime as dropoff_datetime,
								tpep_pickup_datetime as pickup_datetime,
								trip_distance as trip_distance,
								passenger_count as passenger_count,
								total_amount as total_amount
						from 'data/raw/taxi_trips_2023-03.parquet'
				);
		"""

		conn = duckdb.connect(os.getenv("DUCKDB_DATABASE"))
		conn.execute(sql_query)

@asset(
	deps=["taxi_zones_file"]
)
def taxi_zones():
    """
    The raw taxi zones dataset, loaded into a DuckDB database
    """
    sql_query = """
        create or replace table zones as (
                select
                        LocationID as zone_id,
                        zone as zone,
                        borough as borough,
                        the_geom as geometry
                from 'data/raw/taxi_zones.csv'
        );
    """

    conn = duckdb.connect(os.getenv("DUCKDB_DATABASE"))
    conn.execute(sql_query)

@asset(
	deps=["taxi_trips"]
)
def trips_by_week():
    if os.path.exists(constants.TRIPS_BY_WEEK_FILE_PATH):
        os.remove(constants.TRIPS_BY_WEEK_FILE_PATH)

    query = """
        select
            date_trunc('week', dropoff_datetime) as period,
            count(*) as num_trips,
            sum(passenger_count) as passenger_count,
            sum(total_amount) as total_amount,
            sum(trip_distance) as trip_distance
        from trips
        group by period
        order by period desc
    """

    conn = duckdb.connect(os.getenv("DUCKDB_DATABASE"))
    chunk_size = 3
    offset = 0
    header_val = True
    with open(constants.TRIPS_BY_WEEK_FILE_PATH, 'w') as output_file:
        while True:
            chunk_query = f"{query} offset {offset} limit {chunk_size}"
            chunk_result = conn.execute(chunk_query).fetch_df()
            if chunk_result.empty:
                break 
            offset += chunk_size
            output_file.write(chunk_result.to_csv(index=False, header=header_val))
            header_val = False
import csv
import inspect
import logging
import os
import random
import tempfile
from xml.sax.saxutils import escape

from osgeo import gdal
from dbfread import DBF
import pgdata

class RollbackDistributor(object):
    def __init__(self, **age_proportions):
        self._rand = random.Random()
        self._ages = []
        for age, proportion in age_proportions.iteritems():
            self._ages.extend([age] * int(100.00 * proportion))

        self._rand.shuffle(self._ages)
        self._choices = {age: 0 for age in age_proportions.keys()}

    def __str__(self):
        return str(self._choices)

    def next(self):
        age = self._rand.choice(self._ages)
        self._choices[age] += 1
        return int(age)


def rollback_age_disturbed(db_url, config):
    """ Calculate pre-disturbance age and rollback inventory age
    """
    dist_age_prop_path = config.GetDistAgeProportionFilePath()
    logging.info("Calculating pre disturbance age using '{}' to select age"
                 .format(dist_age_prop_path))
    # Calculating pre-disturbance age is one execution per grid cell record
    # It should be possible to apply the update to all cells at once...
    # Maybe using this approach?
    # https://dba.stackexchange.com/questions/55363/set-random-value-from-set/55364#55364
    dist_age_props = {}
    with open(dist_age_prop_path, "r") as age_prop_file:
        reader = csv.reader(age_prop_file)
        reader.next()  # skip header
        for dist_type, age, prop in reader:
            dist_type = int(dist_type)
            dist_ages = dist_age_props.get(dist_type)
            if not dist_ages:
                dist_age_props[dist_type] = {}
                dist_ages = dist_age_props[dist_type]
            dist_ages[age] = float(prop)
    age_distributors = {}
    for dist_type, age_props in dist_age_props.iteritems():
        age_distributors[dist_type] = RollbackDistributor(**age_props)
    db = pgdata.connect(db_url)
    for row in db['preprocessing.inventory_disturbed']:
        age_distributor = age_distributors.get(dist_type)
        # logging.info("Age picks for disturbance type {}:{}".format(
        # dist_type, str(age_distributor)))
        sql = """
            UPDATE preprocessing.inventory_disturbed
            SET pre_dist_age = %s
            WHERE grid_id = %s
        """
        db.execute(sql, (age_distributor.next(), row['grid_id']))


    logging.info("Calculating rollback inventory age")
    sql = """
        UPDATE preprocessing.inventory_disturbed
        SET rollback_age = pre_dist_age + (%s - new_disturbance_yr)
    """
    db = pgdata.connect(db_url)
    db.execute(sql, (config.GetRollbackRange()["StartYear"]))



def rollback_age_non_disturbed(db_url, config):
    """ Roll back age for undisturbed stands
    """
    logging.info('Rolling back ages for age {}'.format(
        config.GetRollbackRange()["StartYear"]))
    sql_path = os.path.join(os.path.dirname(inspect.stack()[0][1]), 'sql')
    db = pgdata.connect(db_url, sql_path=sql_path)
    db['preprocessing.inventory_rollback'].drop()
    db.execute(
        db.queries['inventory_rollback'],
        (config.GetInventoryYear(), config.GetRollbackRange()["StartYear"]))


def generate_slashburn(db_url, config):
    """
    Generate annual slashburn disturbances for the rollback period.

    Note:
    slashburn disturbances are written as grid cells to preprocessing.temp_slashburn
    (this lets us use the same query to generate slashburn for rollback and historic)
    """
    rollback_start = config.GetRollbackRange()["StartYear"]
    rollback_end = config.GetRollbackRange()["EndYear"]
    slashburn_percent = config.GetSlashBurnPercent()
    logging.info('Generating slashburn for {}-{} as {} of annual harvest area'.format(
        rollback_start,
        rollback_end,
        slashburn_percent))
    sql_path = os.path.join(os.path.dirname(inspect.stack()[0][1]), 'sql')
    db = pgdata.connect(db_url, sql_path=sql_path)
    db['preprocessing.temp_slashburn'].drop()
    db.execute("""
        CREATE TABLE preprocessing.temp_slashburn
        (slashburn_id serial primary key,
         grid_id integer,
         dist_type integer,
         year integer)
    """)
    for year in range(rollback_start, rollback_end + 1):
        db.execute(db.queries['create_slashburn'], (year, slashburn_percent))

def export_rollback_disturbances(gdal_con, config, region_path):
    """ Export rolled back disturbances to shapefile
    """
    rollback_disturbances_output = config.GetRollbackDisturbancesOutputDir(region_path)
    logging.info(
        'Exporting rollback disturbances to {}'.format(rollback_disturbances_output)
    )
    # create output folder if it does not exist
    dirname = os.path.dirname(rollback_disturbances_output)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    # aggregate the disturbances by grid, dist_type, year, regen delay, and dump
    # only cells where a disturbance has occured
    sql = """
        SELECT
          i.grid_id AS cell_id,
          i.dist_type AS {dist_type},
          i.new_disturbance_yr AS {dist_yr},
          i.regen_delay AS {regen},
          ST_Union(g.geom) as geom
        FROM preprocessing.inventory_rollback i
        INNER JOIN preprocessing.inventory_grid_xref x
        ON i.grid_id = x.grid_id
        INNER JOIN preprocessing.grid g
        ON x.grid_id = g.grid_id
        WHERE i.new_disturbance_yr IS NOT NULL
        GROUP BY
          i.grid_id,
          i.dist_type,
          i.new_disturbance_yr,
          i.regen_delay
        UNION ALL
        SELECT
          i.grid_id AS cell_id,
          i.dist_type AS {dist_type},
          i.year AS {dist_yr},
          0 AS {regen},
          ST_Union(g.geom) as geom
        FROM preprocessing.temp_slashburn i
        INNER JOIN preprocessing.inventory_grid_xref x
        ON i.grid_id = x.grid_id
        INNER JOIN preprocessing.grid g
        ON x.grid_id = g.grid_id
        WHERE i.year IS NOT NULL
        GROUP BY
          i.grid_id,
          i.dist_type,
          i.year
    """.format(dist_type=config.GetInventoryField('dist_type'),
               dist_yr=config.GetInventoryField('new_disturbance_yr'),
               regen=config.GetInventoryField('regen_delay'))
    # gdal.VectorTranslate option SQLStatement doesn't seem to pick up that we want to
    # use the PG driver's sql - it seems to be using OGRSQL so it throws errors when
    # trying to use ST_Union and similar
    # Lets just create a VRT as as work-around
    out_layer = os.path.splitext(os.path.basename(rollback_disturbances_output))[0]
    vrtpath = _create_pg_vrt(gdal_con, sql, out_layer)
    gdal.VectorTranslate(
        rollback_disturbances_output,
        vrtpath,
        accessMode='overwrite')


def export_inventory(db_url, gdal_con, config, region_path):
    """ Export classifiers and rolled back age to file (raster)
    """
    raster_output = config.GetInventoryRasterOutputDir(region_path)
    logging.info(
        'Exporting inventory rasters to {}'.format(raster_output)
    )

    if not os.path.exists(raster_output):
        os.makedirs(raster_output)

    # initialize raster meta, recording info about each raster that gets dumped
    raster_meta = []

    # rasterize age, it comes from the 'inventory_disturbed' table
    sql = """
        SELECT r.rollback_age as age, g.geom
        FROM preprocessing.grid
        INNER JOIN preprocessing.inventory_disturbed i
        ON g.grid_id = i.grid_id
    """
    vrtpath = _create_pg_vrt(gdal_con, sql, 'age')
    src_age_col = config.GetInventoryFieldNames()["age"]
    file_path = os.path.join(raster_output, "{}.tif".format(src_age_col))
    gdal.Rasterize(
        file_path,
        vrtpath,
        xRes=config.GetResolution(),
        yRes=config.GetResolution(),
        attribute='age',
        allTouched=True,
        # noData=255,  # nodata shown as 255 in line 69 of 03_tiler/tiler.py
        creationOptions=["COMPRESS=DEFLATE"]
    )
    raster_meta.append(
        {
            "file_path": file_path,
            "attribute": src_age_col,
            "attribute_table": None
        }
    )

    # rasterize inventory and reporting classifiers, plus species
    reporting_classifiers = config.GetReportingClassifiers()
    inventory_classifiers = config.GetInventoryClassifiers()
    to_rasterize = reporting_classifiers.copy()      # start with reporting keys/values
    to_rasterize.update(inventory_classifiers)       # modify with inventory keys/values
    to_rasterize["species"] = config.GetInventoryFieldNames()["species"]   # add species

    # define classifier types which do not require attribute dicts
    integer_types = ('SMALLINT', 'BIGINT', 'INTEGER')
    db = pgdata.connect(db_url)

    raster_meta = []
    for attribute, field_name in to_rasterize.items():
        file_path = os.path.join(raster_output, "{}.tif".format(attribute))
        # do not create a lookup/attribute table for integer fields
        if db['preprocessing.inventory'].column_types[field_name] in integer_types:
            sql = """
                SELECT i.{}, g.geom
                FROM preprocessing.grid g
                INNER JOIN preprocessing.inventory_grid_xref x
                ON g.grid_id = x.grid_id
                INNER JOIN preprocessing.inventory i
                ON x.inventory_id = i.inventory_id
            """.format(field_name)
            attribute_table = None
        # for non-int types, create lookup and rasterize with the integer lookup value
        else:
            # create lookup
            db['preprocessing.inventory_{col}_xref'].drop()
            lut_sql = """
            WITH attrib AS
            (
             SELECT DISTINCT {col}
             FROM preprocessing.inventory
             ORDER BY {col}
            )
            CREATE TABLE preprocessing.inventory_{col}_xref
            SELECT
              row_number() over() as val,
              {col}
            FROM attrib
            """
            db.execute(lut_sql)
            # generate sql for rasterization
            sql = """
                SELECT lut.val, g.geom
                FROM preprocessing.grid g
                INNER JOIN preprocessing.inventory_grid_xref x
                ON g.grid_id = x.grid_id
                INNER JOIN preprocessing.inventory i
                ON x.inventory_id = i.inventory_id
                INNER JOIN preprocessing.inventory_{col}_xref lut
                ON i.{col} = lut.{col}
            """.format(col=field_name)
            # generate attribute lookup dict by iterating through table rows
            attribute_table = {}
            for row in db['preprocessing.inventory_'+field_name+"_xref"]:
                attribute_table[row['val']] = list(row[field_name])

        vrtpath = _create_pg_vrt(gdal_con, sql, attribute)
        gdal.Rasterize(
            file_path,
            vrtpath,
            xRes=config.GetResolution(),
            yRes=config.GetResolution(),
            attribute=field_name,
            allTouched=True,
            # noData=255,  # nodata shown as 255 in line 69 of 03_tiler/tiler.py
            creationOptions=["COMPRESS=DEFLATE"]
        )

        raster_meta.append(
            {
                "file_path": file_path,
                "attribute": attribute,
                "attribute_table": attribute_table
            }
        )
    return raster_meta



def _create_pg_vrt(gdal_con, sql, out_layer):
    """ Create a quick temp vrt file pointing to layer name, pg connection and query
    """
    vrt = """<OGRVRTDataSource>
               <OGRVRTLayer name="{layer}">
                 <SrcDataSource>{pgcred}</SrcDataSource>
                 <SrcSQL>{sql}</SrcSQL>
               </OGRVRTLayer>
             </OGRVRTDataSource>
          """.format(layer=out_layer,
                     sql=escape(sql.replace("\n", " ")),
                     pgcred=gdal_con)
    vrtpath = os.path.join(tempfile.gettempdir(), "pg_dump.vrt")
    if os.path.exists(vrtpath):
        os.remove(vrtpath)
    with open(vrtpath, "w") as vrtfile:
        vrtfile.write(vrt)
    return vrtpath


def _create_attribute_table(dbf_path, field_name):
    """
    Create an attribute table with the field name given to be used in the tiler along
    with the tif. This is necessary for fields that are not integers.
    """
    attr_table = {}
    for row in DBF(dbf_path):
        if len(row) < 3:
            return None
        attr_table.update({row.items()[0][1]: [row.items()[-1][1]]})
    return attr_table



def _load_dist_age_prop(db_url, dist_age_prop_path):
    """
    Load disturbance age csv data to postgres
    Currently not used but could be useful to speed up calculatePreDistAge
    (or perhaps just read the csv to strings that get inlined into pg arrays)
    """
    db = pgdata.connect(db_url)
    db['preprocessing.dist_age_prop'].drop()
    db.execute("""CREATE TABLE preprocessing.dist_age_prop
                  (dist_type_id integer, age integer, proportion numeric)""")
    with open(dist_age_prop_path, "r") as age_prop_file:
        reader = csv.reader(age_prop_file)
        reader.next()  # skip header
        for dist_type, age, prop in reader:
            db.execute("""
                INSERT INTO preprocessing.dist_age_prop
                (dist_type_id, age, proportion)
                VALUES (%s, %s, %s)
            """, (dist_type, age, prop))

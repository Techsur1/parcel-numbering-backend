from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from geopandas import GeoDataFrame, read_file
import zipfile, os, shutil, tempfile

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://technicalsurveyor.in", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process-shapefile/")
async def process_shapefile(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files allowed")
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "input.zip")
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        extract_dir = os.path.join(temp_dir, "shapefile")
        os.makedirs(extract_dir)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
        shp_files = [f for f in os.listdir(extract_dir) if f.endswith(".shp")]
        if not shp_files:
            raise HTTPException(status_code=400, detail="No .shp file found")
        gdf = read_file(os.path.join(extract_dir, shp_files[0]))
        if len(gdf) < 2:
            raise HTTPException(status_code=400, detail="Shapefile must have village and parcels")
        village = gdf.iloc[0]
        parcels = gdf.iloc[1:].copy()
        if not all(parcels.geometry.within(village.geometry)):
            raise HTTPException(status_code=400, detail="Parcels outside village")
        parcels["pos_point"] = parcels.geometry.representative_point()
        parcels["y"] = parcels["pos_point"].y
        parcels["x"] = parcels["pos_point"].x
        parcels = parcels.sort_values(by=["y", "x"], ascending=[False, True])
        parcels["parcel_id"] = range(1, len(parcels) + 1)
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)
        output_shp = os.path.join(output_dir, "numbered_parcels.shp")
        parcels[["geometry", "parcel_id"]].to_file(output_shp)
        output_zip = os.path.join(temp_dir, "numbered_parcels.zip")
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for ext in ["shp", "shx", "dbf", "prj"]:
                file_path = os.path.join(output_dir, f"numbered_parcels.{ext}")
                if os.path.exists(file_path):
                    zipf.write(file_path, f"numbered_parcels.{ext}")
        with open(output_zip, "rb") as f:
            zip_content = f.read()
        geojson = parcels[["geometry", "parcel_id"]].__geo_interface__
        return {"message": "Success", "geojson": geojson, "download": zip_content.hex()}
cwlVersion: v1.2
class: Workflow
label: opera_water_mask_to_cog workflow

inputs:
  short_name: string
  temporal: string
  bbox: string
  limit: int
  granule_ur: string
  tile: int
  compress: string
  overview_resampling: string
  out_name: string
  idx_window: string
  s3_url: string

outputs:
  out:
    type: Directory
    outputSource: run_app/out

steps:
  run_app:
    run: application.cwl
    in:
      short_name: short_name
      temporal: temporal
      bbox: bbox
      limit: limit
      granule_ur: granule_ur
      tile: tile
      compress: compress
      overview_resampling: overview_resampling
      out_name: out_name
      idx_window: idx_window
      s3_url: s3_url
    out:
      - out

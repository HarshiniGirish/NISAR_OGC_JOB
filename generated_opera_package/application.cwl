cwlVersion: v1.2
class: CommandLineTool
label: opera_water_mask_to_cog

baseCommand:
  - /opt/app/run.sh

inputs:
  short_name:
    type: string
    default: "OPERA_L3_DISP-S1_V1"
    inputBinding:
      prefix: --short-name
  temporal:
    type: string
    default: "2016-07-01T00:00:00Z,2024-12-31T23:59:59Z"
    inputBinding:
      prefix: --temporal
  bbox:
    type: string
    default: ""
    inputBinding:
      prefix: --bbox
  limit:
    type: int
    default: 10
    inputBinding:
      prefix: --limit
  granule_ur:
    type: string
    default: ""
    inputBinding:
      prefix: --granule-ur
  tile:
    type: int
    default: 256
    inputBinding:
      prefix: --tile
  compress:
    type: string
    default: "DEFLATE"
    inputBinding:
      prefix: --compress
  overview_resampling:
    type: string
    default: "nearest"
    inputBinding:
      prefix: --overview-resampling
  out_name:
    type: string
    default: "water_mask_subset.cog.tif"
    inputBinding:
      prefix: --out-name
  idx_window:
    type: string
    default: "0:1024,0:1024"
    inputBinding:
      prefix: --idx-window
  s3_url:
    type: string
    default: ""
    inputBinding:
      prefix: --s3-url

outputs:
  out:
    type: Directory
    outputBinding:
      glob: output

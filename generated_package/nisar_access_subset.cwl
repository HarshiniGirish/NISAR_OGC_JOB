cwlVersion: v1.2
class: CommandLineTool
label: nisar_access_subset

baseCommand:
  - /opt/app/run.sh

inputs:
  access_mode:
    type: string
    default: "s3"
    inputBinding:
      prefix: --access_mode
  s3_href:
    type: string
    default: "s3://sds-n-cumulus-prod-nisar-products/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_003_005_D_077_4005_DHDH_A_20251017T132451_20251017T132526_X05007_N_F_J_001/NISAR_L2_PR_GCOV_003_005_D_077_4005_DHDH_A_20251017T132451_20251017T132526_X05007_N_F_J_001.h5"
    inputBinding:
      prefix: --s3_href
  https_href:
    type: string
    default: "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_003_005_D_077_4005_DHDH_A_20251017T132451_20251017T132526_X05007_N_F_J_001/NISAR_L2_PR_GCOV_003_005_D_077_4005_DHDH_A_20251017T132451_20251017T132526_X05007_N_F_J_001.h5"
    inputBinding:
      prefix: --https_href
  short_name:
    type: string
    default: "NISAR_L2_GCOV_BETA_V1"
    inputBinding:
      prefix: --short_name
  count:
    type: string
    default: "10"
    inputBinding:
      prefix: --count
  granule_index:
    type: string
    default: "0"
    inputBinding:
      prefix: --granule_index
  asf_s3_creds_url:
    type: string
    default: "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials"
    inputBinding:
      prefix: --asf_s3_creds_url
  vars:
    type: string
    default: "HHHH"
    inputBinding:
      prefix: --vars
  group:
    type: string
    default: "/science/LSAR/GCOV/grids/frequencyA"
    inputBinding:
      prefix: --group
  x_path:
    type: string
    default: "/science/LSAR/GCOV/grids/frequencyA/xCoordinates"
    inputBinding:
      prefix: --x_path
  y_path:
    type: string
    default: "/science/LSAR/GCOV/grids/frequencyA/yCoordinates"
    inputBinding:
      prefix: --y_path
  bbox:
    type: string
    default: "750000,2450000,800000,2500000"
    inputBinding:
      prefix: --bbox
  bbox_crs:
    type: string
    default: "EPSG:32643"
    inputBinding:
      prefix: --bbox_crs
  out_name:
    type: string
    default: "nisar_subset.zarr"
    inputBinding:
      prefix: --out_name

outputs:
  out:
    type: Directory
    outputBinding:
      glob: output

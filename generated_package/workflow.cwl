cwlVersion: v1.2
class: Workflow
label: nisar_access_subset workflow

inputs:
  access_mode: string
  https_href: string
  s3_href: string
  short_name: string
  count: int
  granule_index: int
  asf_s3_creds_url: string
  group: string
  vars: string
  x_path: string
  y_path: string
  bbox: string
  bbox_crs: string
  allow_full_granule: boolean
  out_name: string

outputs:
  out:
    type: Directory
    outputSource: run_app/out

steps:
  run_app:
    run: application.cwl
    in:
      access_mode: access_mode
      https_href: https_href
      s3_href: s3_href
      short_name: short_name
      count: count
      granule_index: granule_index
      asf_s3_creds_url: asf_s3_creds_url
      group: group
      vars: vars
      x_path: x_path
      y_path: y_path
      bbox: bbox
      bbox_crs: bbox_crs
      allow_full_granule: allow_full_granule
      out_name: out_name
    out:
      - out

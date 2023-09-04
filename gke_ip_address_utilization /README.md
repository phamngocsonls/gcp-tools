
# GKE IP address utilization

Small tool to calculate GKE IP address utilization, support Shared VPC

### Requirements
* IAM roles:
	* roles/bigquery.jobUser (Cloud Asset Inventory project)
	* roles/monitoring.viewer (ORG)
* Export Cloud Asset Inventory to BigQuery: https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery
* Update variables in `main.py`:
	* project_env: In case you have a multi-environment network and the network CIDR may be duplicated (Shared VPC)
	* location: GKE cluster location
	* gcp_asset_dataset: GCP Cloud Asset Inventory dataset in BigQuery

![Alt text](https://github.com/phamngocsonls/gcp-tools/blob/main/image/gke_ip_address_utilization_1.jpeg?raw=true "Demo")

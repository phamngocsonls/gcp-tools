from google.cloud import bigquery
from google.cloud import monitoring_v3
import time
import ipaddress
import threading

def round_to_nearest_multiple(number):
    start = 1
    while True:
        if start >= number:
            return start
        start = start*2

def get_node_from_monitoring(start_time,end_time,project_id):
    global node_pool_count_dict
    project_name = f"projects/{project_id}"
    interval = monitoring_v3.TimeInterval()
    nanos = 0
    metric_type = ''
    interval = monitoring_v3.TimeInterval(
        {
            "end_time": {"seconds": end_time, "nanos": nanos},
            "start_time": {"seconds": start_time, "nanos": nanos},
        }
    )
    filter = 'metric.type = ' + '"' + "kubernetes.io/node_daemon/cpu/core_usage_time" + '"'
    request={
        "name": project_name,
        "filter": filter,
        "interval": interval,
        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
    }

    for i in range(0,2):
        try:
            client = monitoring_v3.MetricServiceClient()
            results = client.list_time_series(request=request,timeout=300)
            break
        except:
            continue

    
    data_list = []
    for i in results:
        resource_name  = list(str(i.resource).split("\n"))
        for i in range(0,len(resource_name)):
            if str(resource_name[i]).find('key: "project_id"') > -1:
                project_id = str(resource_name[i+1][resource_name[i+1].find('"')+1:-1])
            elif str(resource_name[i]).find('key: "cluster_name"') > -1:
                cluster_name = str(resource_name[i+1][resource_name[i+1].find('"')+1:-1])
            elif str(resource_name[i]).find('key: "node_name"') > -1:
                node_name = str(resource_name[i+1][resource_name[i+1].find('"')+1:-1])
        

        node_name_strip = node_name[node_name.find(cluster_name)+len(cluster_name)+1:-14]
        key = project_id + "_" + cluster_name + "_" + node_name
        if key not in data_list:
            data_list.append(key)


    for i in data_list:
        temp_list = i.split("_")
        node_name_strip = temp_list[-1][temp_list[-1].find(temp_list[1])+len(temp_list[1])+1:-14]
        new_key = temp_list[0] + "_" + temp_list[1] + "_" +  node_name_strip 
        if new_key not in node_pool_count_dict:
            node_pool_count_dict[new_key] = 1
        else:
            node_pool_count_dict[new_key] = node_pool_count_dict[new_key] + 1

    return node_pool_count_dict

if __name__ == "__main__":
    project_env = {"non-prod-network":["project_1","project_2"],"prod-network":["project_A","project_B"]}  #update_here
    location = "asia-east1"                            #update_here
    gcp_asset_dataset = ""    #update_here  #https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#organizations
    csv_header = "project_env,ip_cidr,subnet_ip_util,used_by"

    with open("report.csv", 'w') as out:
        out.write(csv_header + '\n')

    for pje in project_env:
        project_list = []
        node_pool_query = """
        SELECT 
        REGEXP_EXTRACT(CAST(name AS STRING), r'projects\/(.*?)\/') as project_id,
        REGEXP_EXTRACT(CAST(name AS STRING), r'\/clusters\/([^\/]+)\/') as cluster,
        REGEXP_EXTRACT(CAST(name AS STRING), r'nodePools\/(.*?)$') as node_pool,
        resource.location,
        REGEXP_EXTRACT(CAST(resource.data AS STRING), r'"networkConfig":\s*\{\s*(.*?)\s*\}') as network_config,
        REGEXP_EXTRACT(CAST(resource.data AS STRING), r'"maxPodsConstraint":\s*\{\s*(.*?)\s*\}') as max_pod,
        FROM `gcp_asset_dataset.resources` where asset_type = "container.googleapis.com/NodePool"
        """
        node_pool_query = node_pool_query.replace("gcp_asset_dataset",gcp_asset_dataset)

        client_bq = bigquery.Client()
        query_job = client_bq.query(node_pool_query)  # Make an API request.
        rows = query_job.result()
        pod_ip_dict = {}
        node_max_pod = {}
        for row in rows:
            if row['project_id'] not in project_list and row['project_id'] in project_env[pje] and row['location'] == location:
                project_list.append(row['project_id'])
            key = row['project_id'] + "_" + row['cluster'] + "_" + row['node_pool']
            max_pod = int(row['max_pod'][row['max_pod'].find(":")+2:-1])
            network_config = row['network_config']
            pod_range = network_config[network_config.find("podIpv4CidrBlock")+19:network_config.find("podRange")-3]
            if pod_range not in pod_ip_dict:
                pod_ip_dict[pod_range] =[key]
            else:
                pod_ip_dict[pod_range].append(key)
            node_max_pod[key] = max_pod

        global node_pool_count_dict
        node_pool_count_dict = {}

        thread_list = []
        for i in project_list:
            thread_list.append(threading.Thread(target=get_node_from_monitoring,args=(int(time.time()-120),int(time.time()),i,)))

        for thread in thread_list:
            thread.start()
            time.sleep(0.05)
        for thread in thread_list:
            thread.join()

        for i in pod_ip_dict:
            net = ipaddress.ip_network(i)
            total_ip = net.num_addresses
            total_taken_ip = 0
            pool_count_dict = {}
            for j in pod_ip_dict[i]:
                if j in node_max_pod and j in node_pool_count_dict:
                    pool_count_dict[j] = "max_pod: " + str(node_max_pod[j]) + " - total_node: " + str(node_pool_count_dict[j])
                    count_ip = round_to_nearest_multiple(node_max_pod[j]) * node_pool_count_dict[j] * 2
                    total_taken_ip += count_ip
                
            ip_util = round((total_taken_ip/total_ip)*100,1)
            pool_count_str = ""
            if len(pool_count_dict) > 0:
                for iz in pool_count_dict:
                    pool_count_str += iz + " : " + pool_count_dict[iz] + " | "
            pool_count_str = pool_count_str[:-3]
            output = pje + "," + i + "," + str(ip_util) + "," + pool_count_str
            with open("report.csv", 'a') as out:
                out.write(output + '\n')

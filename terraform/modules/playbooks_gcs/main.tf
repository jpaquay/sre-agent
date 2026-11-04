# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

resource "google_storage_bucket" "playbooks_bucket" {
  name                        = "${var.gcp_project_id}-sre-playbooks"
  location                    = var.gcp_region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
  project                     = var.gcp_project_id

  depends_on = [var.depends_on_apis]
}

locals {
  playbooks = toset([
    "gke-scale-recovery",
    "gke-crashloop-rollback",
    "gke-pod-restart",
    "gke-horizontal-upsize",
    "gke-network-firewall-recovery",
    "gke-service-routing-recovery",
    "gke-dns-recovery",
    "gcp-nat-port-recovery",
    "argolis-cloudrun-iap-recovery",
    "argolis-vertex-quota-failover",
    "argolis-sharedvpc-logsink-recovery",
  ])
}

resource "google_storage_bucket_object" "playbook_files" {
  for_each = local.playbooks
  name     = "playbooks/${each.key}/SKILL.md"
  bucket   = google_storage_bucket.playbooks_bucket.name
  source   = "${abspath(path.root)}/../app/skills/playbooks/${each.key}/SKILL.md"
}

resource "google_storage_bucket_object" "playbook_flat_files" {
  for_each = local.playbooks
  name     = "playbooks/${each.key}.md"
  bucket   = google_storage_bucket.playbooks_bucket.name
  source   = "${abspath(path.root)}/../app/skills/playbooks/${each.key}/SKILL.md"
}

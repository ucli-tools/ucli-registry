#!/usr/bin/env python3
"""
UCLI Registry Version Updater

Automatically updates version fields in apps.yaml by fetching latest commits
from all tool repositories.
"""

import yaml
import requests
import sys
from pathlib import Path
from datetime import datetime
import argparse

class RegistryUpdater:
    def __init__(self, registry_file: str = "registry/apps.yaml"):
        self.registry_file = Path(registry_file)
        self.github_api = "https://api.github.com"

    def load_registry(self):
        """Load the current registry."""
        with open(self.registry_file, 'r') as f:
            return yaml.safe_load(f)

    def save_registry(self, registry):
        """Save the updated registry."""
        with open(self.registry_file, 'w') as f:
            yaml.dump(registry, f, default_flow_style=False, sort_keys=False)

    def get_latest_commit(self, repo_url: str) -> str:
        """Get the latest commit hash from a GitHub repository."""
        try:
            # Extract owner/repo from URL
            if repo_url.startswith("github.com/"):
                repo_path = repo_url.split("github.com/")[1]
            elif "github.com/" in repo_url:
                repo_path = repo_url.split("github.com/")[1].split("/")[0:2]
                repo_path = "/".join(repo_path)
            else:
                return "main"  # fallback

            # API call to get latest commit
            api_url = f"{self.github_api}/repos/{repo_path}/commits/main"
            response = requests.get(api_url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return data['sha'][:12]  # Short commit hash
            else:
                print(f"Warning: Could not fetch commit for {repo_path}")
                return "main"

        except Exception as e:
            print(f"Error fetching commit for {repo_url}: {e}")
            return "main"

    def update_versions(self):
        """Update version fields for all official apps."""
        print("🔄 Updating UCLI Tools registry versions...")

        registry = self.load_registry()

        # Update timestamp
        registry['metadata']['last_updated'] = datetime.now().strftime('%Y-%m-%d')

        # Update official apps
        for app in registry['apps']['official']:
            repo_url = app['repo']
            print(f"  📦 Updating {app['name']} from {repo_url}")

            latest_commit = self.get_latest_commit(repo_url)
            app['version'] = latest_commit

            print(f"    ✅ Updated to {latest_commit}")

        # Save updated registry
        self.save_registry(registry)

        print("✅ Registry update complete!")
        return registry

def main():
    parser = argparse.ArgumentParser(description="Update UCLI Registry versions")
    parser.add_argument("--registry-file", default="registry/apps.yaml",
                       help="Path to registry file")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show changes without saving")

    args = parser.parse_args()

    updater = RegistryUpdater(args.registry_file)

    if args.dry_run:
        # Just show what would be updated
        registry = updater.load_registry()
        for app in registry['apps']['official']:
            repo_url = app['repo']
            latest_commit = updater.get_latest_commit(repo_url)
            print(f"{app['name']}: {app['version']} -> {latest_commit}")
    else:
        # Actually update
        updater.update_versions()

if __name__ == "__main__":
    main()

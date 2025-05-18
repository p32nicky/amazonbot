# Amazon Deal Bot with GitHub Pages - Setup Guide

This guide will walk you through setting up the Amazon Deal Bot that finds products with 50%+ discount, adds your affiliate code, and publishes the deals to GitHub Pages for easy Google Sheets integration.

## What This Bot Does

- Finds Amazon products with 50% or more discount
- Adds your affiliate code (nicdav09-20) to all links
- Saves deals as a CSV file on GitHub Pages
- Runs automatically every 30 minutes
- Provides a consistent URL for Google Sheets integration

## Step 1: Create a GitHub Repository

1. Go to [GitHub.com](https://github.com/) and sign in (or create an account)
2. Click the "+" icon in the top-right corner and select "New repository"
3. Name your repository (e.g., "amazon-deal-bot")
4. Set it to "Public" (required for free GitHub Pages)
5. Check "Add a README file"
6. Click "Create repository"

## Step 2: Upload the Bot Files

1. In your new repository, click "Add file" > "Upload files"
2. Upload the `amazon_deals_github_pages.py` file
3. Add a commit message like "Add Amazon Deal Bot script"
4. Click "Commit changes"

## Step 3: Create the Workflow File

1. In your repository, click "Add file" > "Create new file"
2. For the file name, type `.github/workflows/amazon-deals.yml`
3. Copy and paste the content from the workflow file provided
4. Click "Commit new file"

## Step 4: Create the docs Directory

1. In your repository, click "Add file" > "Create new file"
2. For the file name, type `docs/README.md`
3. Add any content (e.g., "# Amazon Deal Bot")
4. Click "Commit new file"

## Step 5: Enable GitHub Pages

1. Go to your repository's "Settings" tab
2. In the left sidebar, click on "Pages"
3. Under "Source", select "Deploy from a branch"
4. Under "Branch", select "main" and "/docs"
5. Click "Save"
6. Wait a few minutes for GitHub Pages to be enabled

## Step 6: Run the Workflow Manually

1. Go to the "Actions" tab in your repository
2. Click on the "Amazon Deal Bot with GitHub Pages" workflow
3. Click "Run workflow" > "Run workflow"
4. Wait for the workflow to complete (1-2 minutes)

## Step 7: Get Your GitHub Pages URL

1. After the workflow completes, go to the "Code" tab
2. Navigate to the `docs` directory
3. You should see files like `amazon_deals.csv`, `amazon_deals_latest.json`, and `index.html`
4. Your GitHub Pages URL will be:
   ```
   https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/amazon_deals.csv
   ```
   (Replace YOUR-USERNAME with your GitHub username and YOUR-REPO-NAME with your repository name)

## Step 8: Set Up Google Sheets

1. Create a new Google Sheet
2. In cell A1, paste this formula (replace with your actual URL):
   ```
   =IMPORTDATA("https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/amazon_deals.csv")
   ```
3. Press Enter and the sheet will import all the Amazon deals

## Important Notes

1. The workflow will run every 30 minutes and update the CSV file
2. Your Google Sheets formula will always pull the latest data
3. The sheet will show product title, discount percentage, dollar amount off, current price, original price, and affiliate link
4. The first run might take a few minutes for GitHub Pages to activate

## Troubleshooting

If you encounter any issues:

1. **GitHub Pages not working**:
   - Make sure you've selected the correct branch and directory in Settings > Pages
   - Wait a few minutes for changes to propagate
   - Check if the URL format is correct

2. **Workflow failing**:
   - Check the workflow logs in the Actions tab
   - Make sure the python script has the correct permissions
   - Verify that the docs directory exists

3. **Google Sheets not importing**:
   - Make sure your GitHub Pages URL is correct
   - Try accessing the CSV URL directly in your browser first
   - Check that the CSV file exists in your docs directory

4. **No deals found**:
   - The script might occasionally find fewer deals if Amazon's website structure changes
   - Try running the workflow again manually

Enjoy your automated Amazon Deal Bot with GitHub Pages integration!

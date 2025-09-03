# Workday Job Application Automation Tool

An automated job application tool that uses Selenium WebDriver to intelligently fill out Workday job application forms. The tool processes job URLs from a CSV file and automatically applies to jobs using your profile information.

## Features

- **Automated Form Filling**: Intelligently fills out Workday job application forms
- **Batch Processing**: Process multiple job applications from a CSV file
- **Status Tracking**: Tracks application status (pending, applied, failed, error) in CSV
- **Resume Integration**: Automatically uploads and references your resume
- **Human-like Behavior**: Includes random delays and human-like interactions to avoid detection
- **Error Handling**: Comprehensive error handling and logging

## Prerequisites

- Python 3.8 or higher
- Firefox browser installed
- Valid Workday account credentials

## Installation

1. **Clone or download the repository**:
   ```bash
   git clone <repository-url>
   cd workday_automation
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Firefox WebDriver**:
   - The tool uses Firefox with Selenium
   - Make sure Firefox is installed on your system
   - The script will handle the WebDriver setup automatically

## Configuration

### 1. Environment Variables (.env file)

Create a `.env` file in the project root directory with the following variables. This file contains sensitive information and should never be committed to version control.

```env
# ================================
# REQUIRED ENVIRONMENT VARIABLES
# ================================

# Workday Account Credentials (REQUIRED)
# Use the same email and password you use to log into Workday manually
USER_EMAIL='your-email@example.com'
USER_PASSWORD='your-secure-password'

# ================================
# OPTIONAL ENVIRONMENT VARIABLES
# ================================

# Firefox Profile Path (OPTIONAL but RECOMMENDED)
# Using a Firefox profile maintains login sessions and browser preferences
# Leave empty or comment out to use a temporary profile
PROFILE_PATH='/path/to/your/firefox/profile'

# Testing Mode (OPTIONAL)
# Set to 'True' for development/testing, 'False' for production
# When True: Enables additional logging and may skip certain steps
# When False: Full production mode with all automation features
TESTING=True
```

#### Environment Variable Details:

**USER_EMAIL** (Required)
- **Purpose**: Your Workday account email for automatic login
- **Format**: Must be a valid email address
- **Security**: This should match the email you use to manually log into Workday

**USER_PASSWORD** (Required)
- **Purpose**: Your Workday account password for automatic login
- **Security**: Use a strong password and ensure your .env file is secure
- **Note**: The tool will use this to log in automatically to Workday sites

**PROFILE_PATH** (Optional but Recommended)
- **Purpose**: Path to your Firefox profile directory for persistent sessions
- **Benefits**: 
  - Maintains login sessions between runs
  - Preserves browser preferences and extensions
  - Reduces detection risk by using consistent browser fingerprint
  - Faster startup as cookies and cache are preserved
- **Default**: If not set, creates a temporary profile for each run

**TESTING** (Optional)
- **Purpose**: Controls testing vs production behavior
- **Values**: 
  - `True`: Development mode with extra logging
  - `False`: Production mode (default if not specified)
- **Default**: `False`

#### Security Best Practices:

1. **Never commit .env to version control**:
   ```bash
   # Add to your .gitignore file
   .env
   *.env
   ```

2. **Use strong passwords**: Ensure your Workday password is secure

3. **File permissions**: Restrict .env file access:
   ```bash
   chmod 600 .env  # Read/write for owner only
   ```

#### Example .env File:

```env
# Workday Credentials
USER_EMAIL='your-email@example.com'
USER_PASSWORD='your-secure-password'

# Firefox Profile (macOS example)
PROFILE_PATH='/Users/johndoe/Library/Application Support/Firefox/Profiles/abc123def.default-release'

# Development Mode
TESTING=True
```

#### Troubleshooting .env Issues:

- **Login failures**: Check USER_EMAIL and USER_PASSWORD are correct
- **Profile errors**: Ensure PROFILE_PATH points to valid Firefox profile directory
- **Variables not loading**: Ensure .env file is in the project root directory
- **Syntax errors**: Don't use spaces around the = sign, use quotes for values with spaces

### 2. Getting Your Firefox Profile Path

To use a persistent Firefox profile (recommended for maintaining login sessions), you need to find your Firefox profile path:

#### On macOS:
1. Open Firefox
2. Type `about:profiles` in the address bar and press Enter
3. Look for the profile marked as "This is the profile in use"
4. Copy the "Root Directory" path (e.g., `/Users/username/Library/Application Support/Firefox/Profiles/xxxxxxxx.default-release`)
5. Use this path in your `.env` file for the `PROFILE_PATH` variable

#### On Windows:
1. Open Firefox
2. Type `about:profiles` in the address bar and press Enter
3. Look for the profile marked as "This is the profile in use"
4. Copy the "Root Directory" path (e.g., `C:\Users\username\AppData\Roaming\Mozilla\Firefox\Profiles\xxxxxxxx.default-release`)
5. Use this path in your `.env` file for the `PROFILE_PATH` variable

#### On Linux:
1. Open Firefox
2. Type `about:profiles` in the address bar and press Enter
3. Look for the profile marked as "This is the profile in use"
4. Copy the "Root Directory" path (e.g., `/home/username/.mozilla/firefox/xxxxxxxx.default-release`)
5. Use this path in your `.env` file for the `PROFILE_PATH` variable

**Alternative method (Command Line):**
- **macOS/Linux**: Run `find ~ -name "*.default*" -path "*/Firefox/Profiles/*" 2>/dev/null`
- **Windows**: Run `dir "%APPDATA%\Mozilla\Firefox\Profiles" /b` in Command Prompt

**Note**: Using a Firefox profile allows the tool to maintain login sessions and browser preferences, making the automation more reliable.

### 3. Profile Configuration (data/profile.json)

Update the `data/profile.json` file with your personal information:

```json
{
  "email": "your-email@example.com",
  "password": "your-workday-password",
  "complete_name": "Your Full Name",
  "first_name": "Your First Name",
  "family_name": "Your Last Name",
  "address_line_1": "Your City",
  "address_line_2": "Your State",
  "address_state": "Your State",
  "address_city": "Your City",
  "address_postal_code": "12345",
  "phone_number": "123-456-7890",
  "linkedin_url": "https://www.linkedin.com/in/your-profile",
  "github_url": "https://github.com/your-username",
  "personal_website": "https://your-website.com",
  "resume_path": "/path/to/your/resume.pdf",
  "education": "Your Education Details",
  "years_of_experience": "X+",
  "work_experiences": [
    {
      "company": "Company Name",
      "start_year": 2020,
      "start_month": 1,
      "end_year": 2023,
      "end_month": 12,
      "job_title": "Your Job Title",
      "location": "City, State",
      "role_description": "Description of your role and achievements"
    }
  ]
}
```

### 4. Resume Setup

1. Place your resume PDF in the `data/` folder
2. Update the `resume_path` in `data/profile.json` to point to your resume file (e.g., `data/your-resume.pdf`)

### 5. Job URLs CSV File (jobs.csv)

Create a CSV file named `jobs.csv` in the project root with the following structure:

| Column Name | Description | Example |
|-------------|-------------|---------||
| `jobs` | Workday job application URLs | `https://company.wd1.myworkdaysite.com/recruiting/company/job123` |
| `application_status` | Status tracking (auto-generated) | `pending`, `applied`, `failed`, `error` |
| `error_message` | Error details (auto-generated) | Error description if application fails |
| `applied_date` | Application timestamp (auto-generated) | `2024-01-15 14:30:25` |

**Example CSV structure**:
```csv
jobs,application_status,error_message,applied_date
https://company1.wd1.myworkdaysite.com/job1,pending,,
https://company2.wd1.myworkdaysite.com/job2,pending,,
https://company3.wd1.myworkdaysite.com/job3,pending,,
```

**Important Notes**:
- The first column should be named `jobs` and contain the Workday job application URLs
- The tool will automatically add and update the status columns as it processes applications
- Make sure each URL is a direct link to a Workday job application page
- You can start with just the `jobs` column - the other columns will be created automatically

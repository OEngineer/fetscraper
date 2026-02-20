# FetLife Video Scraper

A Python CLI application to download video streams from FetLife with search and filtering capabilities.

## Features

- **Search Videos**: Search FetLife for videos by keyword
- **Profile Downloads**: Download all videos from specific user profiles
- **Duration Filtering**: Filter videos by minimum duration (supports multiple formats)
- **Smart Organization**: Automatically organize downloads by uploader username
- **Resume Support**: Track downloaded videos to avoid duplicates
- **Progress Tracking**: Visual progress bars for downloads
- **Rate Limiting**: Respectful rate limiting to avoid server overload

## Installation

### Prerequisites

- Python 3.8 or higher
- A FetLife account

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd fetscraper
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure credentials:
```bash
cp .env.example .env
# Edit .env and add your FetLife credentials
```

Example `.env` file:
```env
FETLIFE_USERNAME=your_username
FETLIFE_PASSWORD=your_password
DOWNLOAD_PATH=./downloads
```

## Usage

### Test Authentication

Verify your credentials are working:
```bash
python -m src.cli --test-auth
```

### Search and Download Videos

Search for videos by keyword:
```bash
# Basic search
python -m src.cli search "keyword"

# Search with minimum duration (60 seconds)
python -m src.cli search "keyword" --min-duration 60

# Search with time format (5 minutes 30 seconds)
python -m src.cli search "keyword" --min-duration 5:30

# Search with shorthand format
python -m src.cli search "keyword" --min-duration 5m30s

# Limit number of results
python -m src.cli search "keyword" --limit 10

# Custom output directory
python -m src.cli search "keyword" --output /path/to/downloads

# List videos without downloading
python -m src.cli search "keyword" --no-download
```

### Download from User Profile

Download videos from a specific user:
```bash
# By username
python -m src.cli profile username123

# By user ID
python -m src.cli profile 12345

# With minimum duration filter
python -m src.cli profile username123 --min-duration 2:00

# Limit number of videos
python -m src.cli profile username123 --limit 5

# Re-download existing videos
python -m src.cli profile username123 --force
```

### Duration Format Examples

The `--min-duration` option supports multiple formats:

- **Seconds**: `60` (60 seconds)
- **MM:SS**: `5:30` (5 minutes 30 seconds)
- **HH:MM:SS**: `1:23:45` (1 hour 23 minutes 45 seconds)
- **Shorthand**: `5m30s`, `1h30m`, `90s`

## Project Structure

```
fetscraper/
├── src/
│   ├── __init__.py       # Package initialization
│   ├── auth.py           # Authentication handling
│   ├── client.py         # HTTP client with session management
│   ├── config.py         # Configuration management
│   ├── search.py         # Search functionality
│   ├── profile.py        # Profile video extraction
│   ├── downloader.py     # Video download logic
│   ├── utils.py          # Utility functions
│   └── cli.py            # CLI interface (main entry point)
├── downloads/            # Default download directory
├── .env                  # Your credentials (DO NOT COMMIT)
├── .env.example          # Example configuration
├── requirements.txt      # Python dependencies
├── setup.py             # Package setup
└── README.md            # This file
```

## Download Organization

Videos are automatically organized by uploader:

```
downloads/
├── username1/
│   ├── video_title_1_12345.mp4
│   └── video_title_2_67890.mp4
└── username2/
    └── another_video_11111.mp4
```

## Configuration Options

Environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `FETLIFE_USERNAME` | Your FetLife username | Required |
| `FETLIFE_PASSWORD` | Your FetLife password | Required |
| `DOWNLOAD_PATH` | Download directory | `./downloads` |
| `MAX_WORKERS` | Concurrent downloads | `3` |
| `RATE_LIMIT_DELAY` | Delay between requests (seconds) | `5` |
| `DEFAULT_MIN_DURATION` | Default minimum duration filter | `0` |

## Important Notes

### Legal and Ethical Use

- **Personal Use Only**: This tool is for personal, educational use only
- **Respect Privacy**: Only download content you have permission to access
- **Terms of Service**: Use responsibly and in accordance with FetLife's Terms of Service
- **Rate Limiting**: Built-in rate limiting respects FetLife's servers
- **No Redistribution**: Do not redistribute downloaded content

### Technical Considerations

- **Authentication Required**: You must have a valid FetLife account
- **Content Access**: Can only download content visible to your authenticated account
- **JavaScript**: FetLife uses JavaScript heavily; if scraping fails, the site structure may have changed
- **CAPTCHA/2FA**: If your account uses CAPTCHA or 2FA, manual browser login may be required

### Troubleshooting

**Authentication Fails**:
- Verify credentials in `.env` file
- Check if FetLife requires CAPTCHA
- Ensure account is not locked

**No Videos Found**:
- Check search query spelling
- Try broader search terms
- Verify profile username/ID is correct
- Ensure you have access to the content

**Download Errors**:
- Check internet connection
- Verify video is still available
- Check disk space
- Try reducing `MAX_WORKERS` in `.env`

**HTML Parsing Issues**:
- FetLife may have changed their HTML structure
- Check for updates to this tool
- Report issues with example URLs

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests (when implemented)
pytest
```

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

Public domain.

## Disclaimer

This tool is provided as-is for educational and personal use. Users are responsible for complying with FetLife's Terms of Service and applicable laws. The authors are not responsible for misuse of this tool.

## Support

For issues, questions, or contributions, please open an issue on the GitHub repository.

---

**Note**: This is an unofficial tool and is not affiliated with or endorsed by FetLife.

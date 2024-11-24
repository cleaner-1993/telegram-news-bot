import requests
import feedparser
import os
import html
import time
from bs4 import BeautifulSoup

# Embed the API keys directly here (replace with your keys)
API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# CBC Canada News RSS Feed URL
RSS_FEED_URL = 'https://rss.cbc.ca/lineup/canada.xml'

# Gemini API endpoint
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"

# File to store published articles
PUBLISHED_FILE = "published_articles.txt"

def fetch_rss_feed():
    """Fetch the RSS feed and extract entries."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return feed.entries[:5]  # Return the latest 5 entries
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the RSS feed: {e}")
        return []

def read_published_articles():
    """Read the list of previously published article links."""
    if not os.path.exists(PUBLISHED_FILE):
        return set()
    with open(PUBLISHED_FILE, 'r', encoding='utf-8') as file:
        return set(line.strip() for line in file)

def save_published_article(link):
    """Save a new article link to the file."""
    with open(PUBLISHED_FILE, 'a', encoding='utf-8') as file:
        file.write(link + '\n')

def scrape_article(url):
    """Scrape the detailed content of a news article."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the headline (English title)
        headline = soup.find('h1') or soup.find('h2')
        headline = headline.get_text(strip=True) if headline else "No headline found"

        # Find the main content
        body = None
        for class_name in ['content', 'article-body', 'story', 'post', 'entry-content']:
            body_tag = soup.find('div', class_=class_name)
            if body_tag:
                body = body_tag.get_text(strip=True)
                break
        if not body:
            paragraphs = soup.find_all('p')
            body = "\n".join([p.get_text(strip=True) for p in paragraphs]) if paragraphs else "No content found"

        # Find the publication date
        publication_date = None
        time_tag = soup.find('time')
        if time_tag:
            publication_date = time_tag.get_text(strip=True)
        else:
            meta_date = soup.find('meta', {'property': 'article:published_time'})
            publication_date = meta_date.get('content') if meta_date and meta_date.get('content') else "No publication date found"

        return {'headline': headline, 'content': body, 'date': publication_date}
    except Exception as e:
        print(f"Error scraping article: {e}")
        return None


def generate_summary(headline, content):
    """Send the title and content to Gemini API for summarization."""
    headers = {"Content-Type": "application/json"}
    # Prepare input for the API
    data = {
        "contents": [
            {"parts": [{"text": f"Summarize the following story in Persian, using bullets, and provide a clean title without adding terms like 'عنوان' or '##':\n\nTitle: {headline}\n\n{content}"}]}
        ]
    }

    try:
        # Consolidated debug log
        print(f"DEBUG: Sending request to Gemini API with URL: {URL} and payload: {data}")

        # Send request
        response = requests.post(URL, headers=headers, json=data)
        response.raise_for_status()

        # Consolidated response log
        print(f"DEBUG: Received response: {response.status_code}, Content: {response.text}")

        # Parse the response
        result = response.json()
        persian_summary = result["candidates"][0]["content"]["parts"][0]["text"]

        # Process the response to extract the title and summary
        lines = persian_summary.split("\n")
        if len(lines) == 0:
            return None, None

        # Extract and clean the title
        cleaned_title = lines[0].strip()
        unwanted_terms = ["عنوان", "##"]
        for term in unwanted_terms:
            cleaned_title = cleaned_title.replace(term, "").strip()

        # Extract and clean the summary
        cleaned_summary = "\n".join(lines[1:]).strip()

        return cleaned_title, cleaned_summary
    except requests.exceptions.RequestException as e:
        print(f"Error generating summary: {e}")
        return None, None


def extract_image_from_description(description):
    """Extract the image URL from the RSS description tag."""
    try:
        if not description:
            return None  # Return None if description is missing or empty
        soup = BeautifulSoup(description, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']
        return None
    except Exception as e:
        print(f"Error extracting image: {e}")
        return None


def send_message_with_image(photo_url, caption):
    """Send the summary with an image to the Telegram channel, with URL validation and fallback."""
    def is_valid_url(url):
        """Check if a URL is valid and accessible."""
        try:
            response = requests.head(url, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    # Validate the image URL before sending the message
    if not is_valid_url(photo_url):
        print(f"DEBUG: Invalid photo URL: {photo_url}. Falling back to text-only message.")
        send_message(caption)  # Fallback to text-only message
        return

    # Prepare the API call to send the photo
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload = {
        'chat_id': CHANNEL_ID,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()  # Raise an exception for 4xx/5xx errors
        print(f"DEBUG: Successfully sent message with image: {photo_url}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message with image: {e}")
        print("DEBUG: Falling back to text-only message.")
        send_message(caption)  # Fallback to text-only message




def format_bullet_points(summary):
    """Format the bullet points to add spacing between them."""
    # Split the summary into lines, add a blank line after each bullet
    formatted_summary = ""
    for line in summary.split("\n"):
        if line.startswith("*"):
            formatted_summary += f"{line.strip()}\n\n"  # Add an extra newline for spacing
        else:
            formatted_summary += f"{line.strip()}\n"  # Handle non-bullet lines
    return formatted_summary.strip()  # Remove any trailing spaces or newlines

def save_published_article(link):
    """Save a new article link to the file."""
    published_articles = read_published_articles()
    if link not in published_articles:  # Avoid writing duplicates
        with open(PUBLISHED_FILE, 'a', encoding='utf-8') as file:
            file.write(link + '\n')



def post_news_to_channel():
    """Fetch, scrape, summarize, and post news articles with images to the Telegram channel."""
    entries = fetch_rss_feed()
    if not entries:
        print("No entries found in the RSS feed.")
        return

    published_articles = read_published_articles()
    new_articles_found = False  # Flag to track new articles

    for entry in entries:
        link = entry.link

        # Skip if the article has already been posted
        if link in published_articles:
            print(f"Skipping already published article: {link}")
            continue

        # Mark that we found a new article
        new_articles_found = True

        # Scrape the article details
        article = scrape_article(link)
        if not article:
            print(f"Failed to scrape article: {link}")
            continue

        # Generate the Persian title and summary
        persian_title, summary = generate_summary(article['headline'], article['content'])
        if not persian_title or not summary:
            print(f"Failed to generate summary for: {link}")
            continue

        # Format the summary with spacing between bullet points
        formatted_summary = format_bullet_points(summary)

        # Add the red dot (🔴) to the Persian title
        persian_title_with_dot = f"🔴 {persian_title}"

        # Prepare the caption
        caption = f"<b>{html.escape(persian_title_with_dot)}</b>\n\n{html.escape(formatted_summary)}\n\n<a href='{html.escape(link)}'>بیشتر بخوانید</a>"

        # Safely handle entry.description
        description = getattr(entry, "description", None)
        image_url = extract_image_from_description(description)

        # Send the message to the Telegram channel
        if image_url:
            send_message_with_image(image_url, caption)
        else:
            send_message(caption)  # Fallback to text-only if no image is found

        # Save the article link to avoid reposting
        save_published_article(link)

        time.sleep(2)

    # Exit gracefully if no new articles were found
    if not new_articles_found:
        print("No new articles to post. Exiting.")



if __name__ == "__main__":
    post_news_to_channel()

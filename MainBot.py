import discord
import feedparser
import re
import asyncio
from bs4 import BeautifulSoup
import json


#TODO: Check last chapter from same thread, ADD role subscription with emote, ADD Role creation if doesnt exist, FUTURE: Add thread creation if it doesnt exist.

# Set up some variables
TOKEN = "MTA5Mzk4NTY4NTI4MDY2NTY3MA.GH59CR.3aAxLotJbeX1JnYRXFGZfQLLuHsAyUI668DJTc"  # Replace with your Discord bot token
MANGA_LIST_FILE = "manga_list.json"
MANGA_FEED_URL = "http://fetchrss.com/rss/643070db070000260a486653643073064801940d4f7ac6d3.xml"  # Replace with the URL of the manga RSS feed you want to monitor
CHANNEL_ID = 1093972838022647918
MANGA_LIST = {}  # Replace with the name of the manga you want to filter for
UPDATE_INTERVAL = 21600  # Replace with the desired interval in seconds between each check for new releases
SERVER_ID = 201172229793382400

# Create a new Discord client instance with the necessary intents
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

# Define a regular expression pattern to extract the manga name from the title
manga_name_pattern = re.compile(r"^(.+?)(?:\s+Chapter\s+(\d+))?$", re.IGNORECASE)


# Define a function to extract the manga name and chapter number from the entry title
def extract_manga_info(release):
    match = manga_name_pattern.match(release.title)
    if match:
        #get name
        manga_name = match.group(1)
        #get chapter. Default to 0 if it cant be found
        chapter_number = int(match.group(2)) if match.group(2) else 0

        # Get the subtitle (from feed summary). I dont know how this works but I trust
        soup = BeautifulSoup(release.summary, "html.parser")
        #remove ugly FetchRSS watermark
        pattern = re.compile(r'\s*\(Feed generated with FetchRSS\)\s*')
        subtitle = pattern.sub('', soup.text.strip())

        return (manga_name, chapter_number, subtitle, release.link)
    else:
        return None


# Define an async function that checks for new manga releases and posts updates to the designated thread
async def check_manga(server):
    # Initialize the latest chapter to 0
    print(f"Checking for new manga, updating list")

    #load mangas
    try:
        with open(MANGA_LIST_FILE, 'r') as f:
            MANGA_LIST = json.load(f)
    except:
        print(f"File not found")

    while True:
        # Parse the manga RSS feed using feedparser,
        feed = feedparser.parse(MANGA_FEED_URL)

        for entry in feed.entries:
            #LIST INDEXES: 0 Name, 1 chapter, 2 subtitle, 3 link
            manga_attributes = extract_manga_info(entry)
            try:
                # If the latest release has a higher chapter number than the latest chapter we've posted about, it's a new release.
                # Maybe persisting to disk in future
                # If the manga isnt on the list, ignore.
                if MANGA_LIST[manga_attributes[0]] < manga_attributes[1]:
                    # update latest chapter
                    MANGA_LIST[manga_attributes[0]] = manga_attributes[1]
                    # Send a message to the thread with the latest release info and summary
                    thread = discord.utils.get(server.threads, name=manga_attributes[0])  # Find thread corresponding to Manga Name
                    role = discord.utils.get(server.roles, name=manga_attributes[0])  # Find role corresponding to Manga Role

                    # Alert role and post link to thread
                    message = f"New {role.mention} Chapter {manga_attributes[1]}: {manga_attributes[2]}\n{manga_attributes[3]}"
                    print(f" New update: {manga_attributes[0]} - {manga_attributes[1]}")
                    await thread.send(content=message)
                    with open('manga_list.json', 'w') as f:
                        json.dump(MANGA_LIST, f)
            except:
                print(f"Dont care about: {manga_attributes[0]}")

        # Wait before checking for new releases again
        await asyncio.sleep(UPDATE_INTERVAL)

async def check_reactions(server,channel):

    async with discord.Client(intents=discord.Intents.default()) as client:

        # Create a dictionary of roles and their corresponding messages
        role_messages = {}
        async for message in channel.history(limit=None):
            #Add a react to each message for people to hop on
            await message.add_reaction("✅")
            if message.author.bot:
                continue

            # Extract the role name from the message content
            role_name = message.content.split(":")[0].strip()

            # If the role doesn't exist, create it
            role = discord.utils.get(server.roles, name=role_name)
            if role is None:
                role = await server.create_role(name=role_name)

            # Add the message to the dictionary of role messages
            role_messages[role] = message

            # Check if any users have reacted with a :white_check_mark: emoji
            for reaction in message.reactions:
                if str(reaction.emoji) == "✅":
                    users = reaction.users()
                    #Remove all old members
                    for member in role.members:
                        print(f"Removing from role {role.name}: {member}")
                        await member.remove_roles(role)

                    #Readd all members
                    async for user in users:
                        if user.bot:
                            continue
                        if role not in user.roles:
                            print(f"Adding user to {role.name}: {user}")
                            await user.add_roles(role)

    await client.close()

# Define an async event that runs when the bot is ready to start processing events
@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    server = client.get_guild(SERVER_ID)
    channel = server.get_channel(CHANNEL_ID)

    # Check memberships
    await check_reactions(server, channel)

    # Start checking for new manga releases
    await check_manga(server)


# Run the bot with the specified token
client.run(TOKEN)
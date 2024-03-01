import discord
import feedparser
import re
import asyncio
from bs4 import BeautifulSoup
import json

# This allows a discord bot to identify a manga and channel,
# scans the One Piece TCBScans site for new manga updates,
# and posts those updates to the appropriate channels
# (if they exist as a thread under a message mentioning "Manga Title").
# Also creates a role named after the manga, and updates everyone who was
# "subscribed" to the manga by reacting to the message with a white checkmark

#TOD: Create thread if not found.

TOKEN = ""
MANGA_FEED_URL = ""
CHANNEL_ID = 0
UPDATE_INTERVAL = 0
SERVER_ID = 0

SETTINGS={}

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

        # Get the subtitle from feed summary
        soup = BeautifulSoup(release.summary, "html.parser")
        #remove ugly FetchRSS watermark
        pattern = re.compile(r'\s*\(Feed generated with FetchRSS\)\s*')
        subtitle = pattern.sub('', soup.text.strip())

        return (manga_name, chapter_number, subtitle, release.link)
    else:
        return None


# Define an async function that checks for new manga releases and posts updates to the designated thread
async def check_manga(server, manga_list):
    # Initialize the latest chapter to 0
    print(f"Posting new mangas")
    # Parse the manga RSS feed using feedparser,
    feed = feedparser.parse(SETTINGS["MANGA_FEED_URL"])
    print(feed)
    for entry in feed.entries:
        #LIST INDEXES: 0 Name, 1 chapter, 2 subtitle, 3 link
        manga_attributes = extract_manga_info(entry)
        try:
            # If the latest release has a higher chapter number than the latest chapter we've posted about, it's a new release.
            # Maybe persisting to disk in future
            # If the manga isnt on the list, ignore.
            if manga_list[manga_attributes[0]] < manga_attributes[1]:
                # update latest chapter
                manga_list[manga_attributes[0]] = manga_attributes[1]
                # Send a message to the thread with the latest release info and summary
                thread = discord.utils.get(server.threads, name=manga_attributes[0])  # Find thread corresponding to Manga Name
                role = discord.utils.get(server.roles, name=manga_attributes[0])  # Find role corresponding to Manga Role
                # Alert role and post link to thread
                message = f"New {role.mention} Chapter {manga_attributes[1]}: {manga_attributes[2]}\n{manga_attributes[3]}"
                print(f"    New update: {manga_attributes[0]} - {manga_attributes[1]}")
                await thread.send(content=message)

                # Flush updated list
                with open('manga_list.json', 'w') as f:
                    json.dump(manga_list, f)
        except:
            print(f"    Dont care about: {manga_attributes[0]}")

"""
@:param server: The discord guild
@:param channel: The guild's manga channel 
Checks for all messages in the channel's history. 
Associates messages to manga titles and roles.
Removes everyone from manga role and re-adds them if they are still subscribed (removes members who are no longer subscribed)
Adds manga to chapter json if it does not exist.
Creates a role per manga channel if it does not exist.
"""
async def update(guild, channel, manga_list, members_list):
    async with discord.Client(intents=discord.Intents.default()) as client:
        #Check all messages for reaction and role
        async for message in channel.history(limit=None):
            await message.add_reaction("✅")
            role = await update_mangas(message, guild, manga_list)
            await update_members(message,role, guild, members_list)
    await client.close()

async def update_mangas(message, guild, manga_list):
    # If the role doesn't exist, create it
    role = discord.utils.get(guild.roles, name=message.content)
    if role is None:
        role = await guild.create_role(name=role.name)
    # Update tracked mangas and roles
    try:
        # Extract the manga role name from the message content
        manga_list[role.name]  # check if it is in list
    except:
        # Add manga to JSON if not being tracked, but is on the channel
        manga_list[message.content] = 0
    return role

async def update_members(message, role, server, members_list):
    # Check if any users have reacted with a :white_check_mark: emoji
    # gonna have to rework this shit
    # update memberships
    for reaction in message.reactions:
        if str(reaction.emoji) == "✅":
            users=[]
            async for user in reaction.users():
                users.append(user.id)
            manga_members = []
            try:
                #check for if manga is in list
                manga_members = members_list[role.name]
            except:
                #create empty list if not found
                members_list[role.name]=[]

            removed_members = list(set(manga_members) - set(users))
            new_members = list(set(users)-set(manga_members))

            # Remove all old members
            print(f"Resetting role: {role.name}; removed: {removed_members}")
            for member in removed_members:
                print(f"    {member} removed.")
                await server.get_member(member).remove_roles(role)

            print(f"Restoring role: {role.name}; added: {new_members}")
            # Re-add all members
            members_list[role.name] = users
            for user in new_members:
                if user == "TCBScanner":
                    continue
                else:
                    print(f"    User ID: {user} was added.")
                    await server.get_member(user).add_roles(role)
            with open('members_list.json', 'w') as f:
                json.dump(members_list, f)

# Define an async event that runs when the bot is ready to start processing events
@client.event
async def on_ready():
    manga_list = {}
    members_list = {}

    server = client.get_guild(SERVER_ID)
    channel = server.get_channel(CHANNEL_ID)

    #load mangas
    try:
        with open("manga_list.json", 'r') as f:
            manga_list = json.load(f)
    except:
        print(f"Manga list not found, creating new one")
        with open("manga_list.json", 'w') as f:
            json.dump({},f)
            manga_list={}

    # load mangas
    try:
        with open("members_list.json", 'r') as f:
            members_list = json.load(f)
    except:
        print(f"Members list not found, creating new one")
        with open("members_list.json", 'w') as f:
            json.dump({},f)
            manga_list = {}

    while True:
        print(f"Updating lists!")
        # Check memberships
        await update(server, channel, manga_list, members_list)

        print(f"Checking for new mangas..")
        # Start checking for new manga releases
        await check_manga(server, manga_list)

        # Wait before checking for new releases again
        print(f"Done checking, sleeping for {UPDATE_INTERVAL/60} minutes..")
        await asyncio.sleep(UPDATE_INTERVAL)

# Run the bot with the specified token

# load mangas
try:
     with open("settings.json", 'r') as f:
        SETTINGS = json.load(f)

        CHANNEL_ID = SETTINGS["CHANNEL_ID"]
        UPDATE_INTERVAL = SETTINGS["UPDATE_INTERVAL"]
        SERVER_ID = SETTINGS["SERVER_ID"]
        client.run(SETTINGS["TOKEN"])
except:
    print(f"Settings not found, Abort bot")
    exit(1)

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

#FetchRSS updates every 24hrs so the timeout for this bot will be set pretty high.

SETTINGS={}
WRONGANSWERCHANNEL="Wrong Answer"

# Create a new Discord client instance with the necessary intents
intents = discord.Intents.all()
intents.members = True
client = discord.Client(intents=intents)

server=None
channel=None

manga_list={}
manga_name_pattern = re.compile(r"^(.+?)(?:\s+Chapter\s+(\d+))?$", re.IGNORECASE)

# Define a function to extract the manga name and chapter number from the entry title
def extract_manga_info(release):
    match = manga_name_pattern.match(release.title)
    if match:
        #get name
        manga_name = match.group(1)
        #get chapter. Default to 0 if it cant be found
        chapter_number = int(match.group(2)) if match.group(2) else 0

        # Get the subtitle from feed summary. Apparently sometimes there are no subtitles :)
        subtitle = "<No Summary>"
        try:
            soup = BeautifulSoup(release.summary, "html.parser")
            #remove ugly FetchRSS watermark
            pattern = re.compile(r'\s*\(Feed generated with FetchRSS\)\s*')
            subtitle = pattern.sub('', soup.text.strip())
        except:
            print("No Summary Found for: {release.title}")
        return (manga_name, chapter_number, subtitle, release.link)
    else:
        return None

# Define an async function that checks for new manga releases and posts updates to the designated thread
async def check_manga(manga_list):
    # Initialize the latest chapter to 0
    print(f"Posting new mangas")
    # Parse the manga RSS feed using feedparser,
    feed = feedparser.parse(SETTINGS["MANGA_FEED_URL"])
    #print(feed)
    for entry in feed.entries:
        #LIST INDEXES: 0 Name, 1 chapter, 2 subtitle, 3 link
        manga_attributes = extract_manga_info(entry)
        try:
            # If the latest release has a higher chapter number than the latest chapter we've posted about, it's a new release.
            # If the manga isn't on the list, ignore in except.
            if manga_list[manga_attributes[0]]["chapter"] < manga_attributes[1]:
                # update latest chapter
                manga_list[manga_attributes[0]]["chapter"] = manga_attributes[1]
                # Send a message to the thread with the latest release info and summary
                thread = discord.utils.get(channel.threads,name=manga_attributes[0])  # Find thread corresponding to Manga Name
                # Find in archived threads instead
                if not thread:
                    thread = await discord.utils.get(channel.archived_threads(), name=manga_attributes[0])
                role = discord.utils.get(server.roles, name=manga_attributes[0])  # Find role corresponding to Manga Role
                # Alert role and post link to thread
                message = f"New {role.mention} Chapter {manga_attributes[1]}: {manga_attributes[2]}\n{manga_attributes[3]}"
                print(f"    New update: {manga_attributes[0]} - {manga_attributes[1]}")
                await thread.send(message)

                # Flush updated list
                with open('manga_list.json', 'w') as f:
                    json.dump(manga_list, f)
        except Exception as error:
            print(f"    Thread inactive or nonexistent: {manga_attributes[0]}")
            print(error)
"""
@:param server: The discord guild
@:param channel: The guild's manga channel 
Checks for all messages in the channel's history. 
Associates messages to manga titles and roles.
Removes everyone from manga role and re-adds them if they are still subscribed (removes members who are no longer subscribed)
Adds manga to chapter json if it does not exist.
Creates a role per manga channel if it does not exist.
"""
async def update_roles():
    global manga_list, channel,client
    #Check all messages (manga titles) for reaction and role
    async for message in channel.history(limit=None):
        #Make sure they all have a react from the bot:
        await message.add_reaction("✅")
        #test moving this up lol reaction wont be added to new mangas
        role = await update_mangas(message, manga_list)
        await initiate_manga_list(message, role)
    with open('manga_list.json', 'w') as f:
        json.dump(manga_list, f)

async def update_mangas(message, manga_list):

    role = discord.utils.get(server.roles, name=message.content)
    # If the role doesn't exist, create it
    if role is None:
        role = await server.create_role(name=message.content)
    # Update tracked mangas and roles
    try:
        # Extract the manga role name from the message content
        manga_list[role.name]  # check if it is in list
    except:
        # Add manga to JSON if not being tracked, but is on the channel
        manga_list[message.content] = 0
    return role

async def initiate_manga_list(message, role):
    # Check if any users have reacted with a :white_check_mark: emoji
    # gonna have to rework this shit
    # update memberships role=manga role
    global manga_list

    for reaction in message.reactions:
        if (reaction.emoji == "✅"):
            for user in role.members:
                await user.remove_roles(role)

            new_users=[]

            async for user in reaction.users():
                await user.add_roles(role)
                new_users.append(user.id)

            try:
                manga_list[role.name]["members"]=new_users
            except:
                manga_list[role.name]={"members":new_users,"chapter":0}

async def wrongAnswerChecker(member, after):
    # check that there's a nickname
    n = member.name
    if (member.nick != None):
        n = member.nick

    #check don't explode because an owner moved
    role = discord.utils.get(server.roles, name="headhoncho")
    if (after.channel != None and role not in member.roles):
        if (after.channel.name == WRONGANSWERCHANNEL and not re.match(r".*( \(Soaked\)| \(Damp\))$", n)):
            # Maybe keep count of sins, save sin state
            try:
                await member.edit(nick=(n + " (Soaked)"))
                await asyncio.sleep(60)
                await member.edit(nick=n + " (Damp)")
                await asyncio.sleep(300)
                await member.edit(nick=n)
            except Exception as e:
                print("Updating name failed:")
                print(e)
async def updateMangaRole(message,member,add):
    #check that react is on a manga thread
    role = discord.utils.get(server.roles, name=message.content)
    if role:
        if add:
            await member.add_roles(role)
        else:
            await member.remove_roles(role)

async def embedLinks(message):
    if message.author == client.user:
        return
    links = re.findall(r'(https?://\S+)', message.content)
    try:
        for link in links:
            if (('twitter.com' in link or 'tiktok.com' in link) and not link.startswith('https://vx')):
                trimmed_link = re.sub(r'https?://(?:www\.)?', '', link)
                modified_link = 'https://vx' + trimmed_link
                await message.channel.send("Adjusted Twitter/Tiktok link: " + modified_link)
    except Exception as error:
        print(error)
@client.event
async def on_message(message):
    await embedLinks(message)

@client.event
async def on_voice_state_update(member, before, after):
    await wrongAnswerChecker(member,after)

@client.event
async def on_raw_reaction_remove(payload):
    if (payload.emoji.name=='✅'):
        await updateMangaRole(await channel.fetch_message(payload.message_id),server.get_member(payload.user_id),False)

@client.event
async def on_raw_reaction_add(payload):
    if (payload.emoji.name == '✅'):
        await updateMangaRole(await channel.fetch_message(payload.message_id),server.get_member(payload.user_id),True)

@client.event
async def on_ready():
    global server,channel, SETTINGS
    server = client.get_guild(SETTINGS["SERVER_ID"])
    channel = server.get_channel(SETTINGS["CHANNEL_ID"])

    #await startMangas()

async def startMangas():
    global manga_list, SETTINGS
    #load mangas
    try:
        with open("manga_list.json", 'r') as f:
            manga_list = json.load(f)
    except:
        print(f"Manga list not found, creating new one")
        with open("manga_list.json", 'w') as f:
            json.dump({},f)

    print(f"Initiating member lists!")
    # Check memberships
    await update_roles()

    while True:

        print(f"Checking for new mangas..")
        # Start checking for new manga releases
        await check_manga(manga_list)

        # Wait before checking for new releases again
        interval = SETTINGS["UPDATE_INTERVAL"]
        print(f"Done checking, sleeping for {interval/60} minutes..")
        await asyncio.sleep(interval)

# Run the bot with the specified token

# load mangas
try:
    with open("settings.json", 'r') as f:
        SETTINGS = json.load(f)
        client.run(SETTINGS["TOKEN"])

except:
    print(f"Settings not found, Abort bot")
    exit(1)

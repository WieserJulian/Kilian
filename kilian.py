"""
    File name: kilian.py
    Author: Adrian Vinojcic, Tobias Pilz
    This part is responsible for everything related to the discord api.
"""

import argparse
import interactions
import kusss as uni
from database import Database, Roles
import json


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--token", type=str, required=False, dest='token',
                        help="Provide the Discord Bot Token as string.")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    with open("config.json", 'r') as f:
        data = json.load(f)
        bot_token = args.token if args.token is not None else data['token']
        dads = data['dads']

    database = Database()

    bot = interactions.Client(token=bot_token, intents=interactions.Intents.ALL)


    @bot.command()
    @interactions.option(description="Provide the calendar link from KUSSS here.")
    @interactions.option(description="Optionally provide your matriculation number here.")
    async def kusss(ctx: interactions.CommandContext, link: str, studentnumber: str = None):
        """Take advantage of the features provided by Kilian™."""
        try:
            student = uni.student(str(ctx.author.id), link, studentnumber)
            database.insert(student)

            await ctx.send("Welcome on board " + ctx.author.name + "!")

            added_courses = database.get_added_courses(student.discord_id)
            unmanaged_courses = {database.get_course(*entry) for entry in added_courses if
                                 not database.is_managed_course(str(ctx.guild_id), *entry)}
            managed_courses = {database.get_course(*entry) for entry in added_courses if
                               database.is_managed_course(str(ctx.guild_id), *entry)}

            if database.has_category(str(ctx.guild_id)):
                random_guild_channel_id = database.random_guild_channel_id(str(ctx.guild_id))
                random_guild_channel = next(
                    x for x in (await ctx.guild.get_all_channels()) if x.id == random_guild_channel_id)
                category = random_guild_channel.parent_id
            else:
                category = await ctx.guild.create_channel(name="uni", type=interactions.ChannelType.GUILD_CATEGORY)

            added_roles = Roles()
            for course in unmanaged_courses:
                role = await ctx.guild.create_role(course.lva_name)
                channel = await ctx.guild.create_channel(name=course.lva_name, type=interactions.ChannelType.GUILD_TEXT,
                                                         parent_id=category, permission_overwrites=[
                        interactions.Overwrite(id=str(ctx.author.id), type=1,
                                               allow=interactions.Permissions.VIEW_CHANNEL)
                    ])
                added_roles.add((str(ctx.guild_id), str(role.id), str(channel.id), course.lva_nr, course.semester))
            # TODO: Move create_channel out of loop into own loop and create channel / add person to channel if it already exists
            channels = filter(lambda ch:
                              ch.id in map(lambda c:
                                           database.get_channel(str(ctx.guild_id), c.lva_nr, c.semester),
                                           managed_courses),
                              await ctx.guild.get_all_channels())
            for channel in channels:
                channel.permission_overwrites.append(interactions.Overwrite(id=str(ctx.author.id), type=1, allow=interactions.Permissions.VIEW_CHANNEL))

            database.insert(added_roles)

        except uni.InvalidURLException as ex:
            await ctx.send(ex.message, ephemeral=True)


    @bot.command()
    async def unkusss(ctx: interactions.CommandContext):
        """Unsubscribe from the awesome features provided by Kilian™."""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild_id)

        await ctx.send("A pity to see you leave " + ctx.author.name + ". You can join the club anytime with `/kusss`!")
        courses = database.get_added_courses(user_id)
        database.delete_student(user_id)
        roles_to_delete = {database.get_role(guild_id, course[0], course[1]) for course in courses if
                           not database.is_needed_course(*course)}

        for role in roles_to_delete:
            await ctx.guild.delete_role(int(role), "Not needed anymore!")

        database.delete_roles(guild_id, roles_to_delete)


    @bot.command()
    @interactions.option(description="Role you want to ping.")
    @interactions.option(description="Message content goes here.")
    async def ping(ctx: interactions.CommandContext, role: interactions.Role, content: str = ""):
        """Ping everyone partaking that subject."""
        role_id = str(role.id)
        guild_id = str(ctx.guild_id)

        if database.is_managed_role(guild_id, role_id):
            users_with_anonymous_role = database.get_role_members(guild_id, role_id)
        else:
            # TODO: send an ephemeral errormessage
            return NotImplemented

        ping_string = ""
        for user_id in users_with_anonymous_role:
            user = (await ctx.guild.get_member(int(user_id))).user
            ping_string += user.mention

        await ctx.send(ping_string + "\n" + content)

        # POSSIBLE ERROR: too many users, so that not all pings fit in one message
        # POSSIBLE SOLUTION TO ERROR: multiple messages


    @bot.command()
    @interactions.option(description="The user you want the student id of.")
    async def studid(ctx: interactions.CommandContext, member: interactions.Member):
        """Get student id of the specified user."""
        member_id = member.id
        student_id = "get id"
        await ctx.send(student_id, ephemeral=True)


    @bot.command()
    async def sleep(ctx: interactions.CommandContext):
        """Make Kilian go nighty night."""

        if dads.count(str(ctx.author.id)):
            await ctx.send("Good night, daddy!", ephemeral=True)
            await bot._stop()
        else:
            await ctx.send("You are not my daddy!", ephemeral=True)


    @bot.command()
    @interactions.option(description="name of the channel")
    async def test(ctx: interactions.CommandContext, name: str):
        """Create a text channel"""
        from interactions import Permissions as perms
        print(name)
        category = await ctx.guild.create_channel(name="uni", type=interactions.ChannelType.GUILD_CATEGORY,
                                                  permission_overwrites=[
                                                      interactions.Overwrite(id=305009439843549184, type=1,
                                                                             allow=perms.ATTACH_FILES | perms.VIEW_CHANNEL)
                                                  ])
        channel = await ctx.guild.create_channel(name=name, type=interactions.ChannelType.GUILD_TEXT,
                                                 parent_id=category.id, permission_overwrites=[])
        await ctx.send(name)


    @bot.event()
    async def on_message_create(message: interactions.Message):
        """
        Checks if a message contains a managed mention
        If yes: pings all users by replying to the message sent
        If no: returns
        """

        if message.author.id == bot.me.id:
            return

        guild = await message.get_guild()
        guild_id = str(guild.id)
        mentioned_roles = [role_id for role_id in message.mention_roles if database.is_managed_role(guild_id, role_id)]
        if len(mentioned_roles) == 0:
            return

        users_with_anonymous_role = set()
        for role_id in mentioned_roles:
            users_with_anonymous_role = users_with_anonymous_role | database.get_role_members(guild_id, role_id)

        ping_string = ""
        for user_id in users_with_anonymous_role:
            user = (await guild.get_member(int(user_id))).user
            ping_string += user.mention

        await message.reply(ping_string)


    @bot.event()
    async def on_guild_create(guild: interactions.Guild):
        known_users = [user.id for user in guild.members if user.id in database.get_student_ids()]

        for user in known_users:
            print(user)


    @bot.event()
    async def on_start():
        print("Good morning master!")


    bot.start()

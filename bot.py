import asyncio.subprocess
import collections
import datetime
import functools
import hashlib
import io
import logging
import secrets
import sqlite3
import textwrap
import time
import traceback
import types
import discord
import discord.abc
from credentials import BOT_TOKEN
from utils import send_messages, split_message, split_send_message

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)

handler = logging.FileHandler(
        filename='/var/tmp/CPUBot.log', encoding='utf-8', mode='a+')
handler.setLevel(logging.WARNING)
handler.setFormatter(
        logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

handler = logging.FileHandler(
        filename='/var/tmp/CPUBot.verbose.log', encoding='utf-8', mode='a+')
handler.setFormatter(
        logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

bot = discord.Client()

DEBUG = False

guild_id = 615943246706901013


class InterfaceMeta(type):
    def __init__(cls, *args, **kwargs):
        cls._interfaces = {}
        super().__init__(*args, **kwargs)
    
    def __call__(cls, channel: discord.abc.PrivateChannel, *args, **kwargs):
        if channel.id in cls._interfaces:
            return cls._interfaces[channel.id]
        obj = cls.__new__(cls, *args, **kwargs)
        obj.__init__(channel, *args, **kwargs)
        cls._interfaces[channel.id] = obj
        return obj


class BaseInterface(metaclass=InterfaceMeta):
    """
    Each method in subclass of BaseInterface must return a tuple
    The output of split_message is recommended.
    Every interface function must have signature
    (self,command: list, message: discord.Message)
    """
    error_reply = "Error"
    
    def __init__(self, channel: discord.DMChannel):
        self._dispatch_locked = False
        self._channel = channel
    
    def unrecognized_command(self, command) -> str:
        return ("Unrecognized command `%s`." % command) + self.usage
    
    async def dispatch(self, command: str, message) -> list:
        if not self._dispatch_locked:
            try:
                command = command.split()
                func = getattr(self, command[0])
                reply = await func(command[1:] if len(command) > 1 else [],
                                   message)
                if isinstance(reply, str):
                    reply = (reply,)
                return await send_messages(message.author, reply)
            except AttributeError:
                if DEBUG:
                    raise
                return await split_send_message(message.author,
                                                self.error_reply)
            except IndexError:
                return await split_send_message(
                        message.author, 'Insufficient arguments.\n' + self.usage)
        else:
            return []
    
    def lock_dispatch(self):
        self._dispatch_locked = True
    
    def unlock_dispatch(self):
        self._dispatch_locked = False
    
    @property
    def usage(self) -> str:
        res = 'Usage:\n'
        for cls in self.__class__.__mro__:
            for name, attr in cls.__dict__.items():
                if isinstance(attr, types.FunctionType) and hasattr(
                        attr, 'usage'):
                    res += '```' + attr.usage + '```'
                    if hasattr(attr, 'description'):
                        res += attr.description
                    res += '\n\n'
        return res


class Conversation:
    def __init__(self, interface: BaseInterface):
        self.interface = interface
    
    async def __aenter__(self):
        self.interface.lock_dispatch()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is asyncio.TimeoutError:
            await self.send('Operation timed out')
            self.interface.unlock_dispatch()
            return True
        self.interface.unlock_dispatch()
    
    def __enter__(self):
        self.interface.lock_dispatch()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.interface.unlock_dispatch()
    
    async def send(self, msg, enclose_in='', separator='\n', **kwargs):
        """
        :param msg: passed to split_send_message
        :param enclose_in: passed to split_send_message
        :param separator: passed to split_send_message
        :param kwargs: passed to discord.Messageable.send
        :return: messages
        """
        return await split_send_message(self.interface._channel, msg,
                                        enclose_in, separator, **kwargs)
    
    async def recv(self, timeout=1800) -> discord.Message:
        return await bot.wait_for(
                'message',
                check=lambda msg: msg.channel == self.interface._channel and
                                  not msg.author.bot,
                timeout=timeout)


class UserInterface(BaseInterface):
    @property
    def error_reply(self):
        return textwrap.dedent("""
                Sorry I'm not evolved enough to answer your question or even reply properly.
                use the `#general` channel of CPU server for general discussions about programming as well as the club;
                use the `#help` channel if you need any help with your programming project or homework;
                the club leaders and are ready to help––specifically, the leaders are proficient in:
                \t- Python (CPython)
                \t- Java
                \t- C++
                \t- HTML (Hypertext Markup Language)
                \t- CSS (Cascade Style Sheets)
                \t- JS (JavaScript, also known as ECMAScript)
                \t- Bash (Bourne again shell);
                use the `#lounge` channel for memes, jokes, chats, flirting, and everything else.
                Please redirect any question about me to my creator Jerry `pkqxdd#1358`.

                I also support some basic commands. """) + self.usage
    
    @staticmethod
    def next_message(channel):
        def check(msg):
            return msg.channel == channel and not msg.author.bot
        
        return check


class AdminInterface(UserInterface):
    @property
    def error_reply(self):
        return self.usage
    
    async def announcement(self, command, message):
        await make_announcement(self)
        return ()
    
    announcement.usage = 'announcement'
    announcement.description = 'Make announcement (admin privilege)'


@bot.event
async def on_ready():
    print('Logged in as %s' % bot.user.name)
    game = discord.Game("with a wire clipper")
    await bot.change_presence(activity=game)
    global jerry, admins, guild
    jerry = bot.get_user(268759214610972673)
    admins = [
        bot.get_user(191019296229425152),  # Nate
        bot.get_user(516691587695378445), # Di Tieri
        bot.get_user(455832935627751444) # Irie
    ]
    
    admins.append(jerry)
    
    
    guild = discord.utils.find(lambda g: g.id == guild_id, bot.guilds)



@bot.event
async def on_message(message):
    if not message.author.bot:
        if isinstance(message.channel, discord.DMChannel):
            if message.author in admins:
                interface = AdminInterface(message.channel)
            else:
                interface = UserInterface(message.channel)
            try:
                await interface.dispatch(message.content, message)
            except:
                try:
                    await message.author.send(
                            "An error has occurred. My creator has been notified (well, hopefully)."
                    )
                except:
                    pass
                raise


def attach_files(names) -> list:
    l = []
    for filename, display_name in names:
        l.append(discord.File(filename, filename=display_name))
    return l[::
             -1]  # well obviously discord.py uses pop so to retain image orders


async def make_announcement(interface):
    tasks = []
    files = []
    channel = discord.utils.get(guild.channels, name='announcements')
    
    with Conversation(interface) as con:
        await con.send('Commencing announcement mode.')
        await con.send(
                'Please send me the announcement you are about to make. Type `cancel` to cancel.'
        )
        
        message_header = 'Hi $name,\n'
        message_body = (await con.recv()).content
        
        if message_body == 'cancel':
            await con.send("Operation cancelled")
            return
        
        
        await con.send("You are about to make this announcement")
        await con.send('-' * 40)
        await con.send(
                message_header + message_body, files=attach_files(files))
        await con.send('-' * 40)
        await con.send(f"It will be sent to {len(channel.members)} people.")
        await con.send("Confirm? yes/no")
        if (await con.recv()).content.lower() != 'yes':
            await con.send("Operation cancelled")
            return
        
        recipients = []
        for member in channel.members:
            if not member.bot:
                message_header = f"Hi {member.nick},"
                recipients.append(member)
                tasks.append(
                        member.send(
                                message_header + '\n' + message_body,
                                files=attach_files(files)))
        
        tasks.append(
                channel.send(
                        'Hi everyone,\n' + message_body, files=attach_files(files)))
        future = asyncio.gather(*tasks, return_exceptions=True)
        
        callback = functools.partial(
                announcement_succeeded,
                recipients=recipients,
                sender=interface._channel,
                time_started=time.time(),
                embed=discord.Embed(
                        title='Your announcement',
                        description='Hi $name,\n' + message_body))
        future.add_done_callback(callback)
        asyncio.ensure_future(future)


def announcement_succeeded(future, recipients, sender, time_started, embed):
    time_spent = round(time.time() - time_started, 2)
    results = future.result()
    failed_list = []
    errors = []
    try:
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                tb = traceback.format_tb(res.__traceback__)
                tb = '\n'.join(tb)
                errors.append(f'```py\n{str(res)}\n{tb}```')
                failed_list.append(recipients[i])
    except IndexError:
        pass
    
    sch = []
    if not failed_list:
        msg = f"Your announcement has been successfully sent to all {len(recipients)} members in {time_spent} seconds"
        embed.title = msg
        sch.append(sender.send(embed=embed))
    else:
        msg = f"Your announcement has been successfully sent to {len(recipients) - len(failed_list)}/{len(recipients)} members in {time_spent} seconds"
        embed.title = msg
        sch.append(sender.send(embed=embed))
        sch.append(
                split_send_message(
                        sender, 'Failed for:\n' + '\n'.join(m.nick or m.name
                                                            for m in failed_list)))
        sch.append(split_send_message(sender, 'Errors:' + '\n'.join(errors)))
    
    asyncio.ensure_future(asyncio.gather(*sch))


@bot.event
async def on_error(event_method, *args, **kwargs):
    try:
        stacktrace = traceback.format_exc()
        msg = 'Error at `{time}` during handling event `{event}`. Stacktrace: \n```py\n{trace}```\n'.format(
                time=datetime.datetime.now().isoformat(),
                event=event_method,
                trace=stacktrace)
        if args:
            msg += 'Args:\n'
            for arg in args:
                msg += '```{}```\n'.format(arg)
        if kwargs:
            msg += 'Kwargs:\n'
            for key, value in kwargs.items():
                msg += '```{k}: {v}```\n'.format(k=key, v=value)
        await split_send_message(jerry, msg)
    except:
        pass
    finally:
        await discord.Client.on_error(bot, event_method, *args, **kwargs)

if __name__ == '__main__':
    bot.run(BOT_TOKEN)

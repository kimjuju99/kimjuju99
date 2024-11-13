import discord
from discord.ext import commands
from discord.ui import Select, View
import yt_dlp as youtube_dl
import asyncio
import re

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 서버별로 재생 큐와 현재 재생 중인 곡을 저장하는 딕셔너리
queues = {}
current_tracks = {}
panel_messages = {}

ytdl_format_options = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
}
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# URL 형식 확인을 위한 정규표현식
youtube_url_pattern = re.compile(r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/.+')

# 메시지를 임베드로 전송하고 10초 후에 삭제하는 함수
async def send_embed(ctx, title, description):
    embed = discord.Embed(title=title, description=description, color=0x1DB954)
    message = await ctx.send(embed=embed)
    await message.delete(delay=10)  # 10초 후 메시지 삭제

# 패널을 업데이트하는 함수
async def update_panel(ctx):
    """현재 재생 중인 곡 정보로 패널을 업데이트하는 함수"""
    guild_id = ctx.guild.id
    if guild_id in panel_messages and panel_messages[guild_id]:
        embed = discord.Embed(title="음악 컨트롤 패널", description="음악 봇 기능 설명", color=0x1DB954)
        embed.add_field(name="현재 재생 중인 곡 정보", value="현재 재생 중인 노래의 제목과 앨범 커버", inline=False)
        embed.add_field(name="🎵 일시정지", value="현재 재생 중인 음악을 일시정지합니다.", inline=True)
        embed.add_field(name="▶️ 재개", value="일시정지된 음악을 다시 재생합니다.", inline=True)
        embed.add_field(name="⏭️ 스킵", value="현재 곡을 건너뛰고 다음 곡을 재생합니다.", inline=True)
        embed.add_field(name="📜 큐", value="현재 재생 대기 중인 곡 목록을 표시합니다.", inline=True)
        embed.add_field(name="🚪 종료", value="봇이 음성 채널에서 나가도록 합니다.", inline=True)
        
        # 현재 재생 중인 곡 정보 업데이트
        if guild_id in current_tracks and current_tracks[guild_id]:
            embed.add_field(name="지금 재생 중", value=current_tracks[guild_id]['title'], inline=False)
            embed.set_thumbnail(url=current_tracks[guild_id]['thumbnail'])
        
        await panel_messages[guild_id].edit(embed=embed)

# 음악 재생 함수
async def play_music(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        current_tracks[guild_id] = queues[guild_id].pop(0)
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(current_tracks[guild_id]['source'], **ffmpeg_options))
        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_music(ctx), bot.loop))
        
        # 현재 음악 임베드로 표시하고 10초 후에 삭제
        embed = discord.Embed(title="Now Playing", description=current_tracks[guild_id]['title'], color=0x1DB954)
        embed.set_thumbnail(url=current_tracks[guild_id]['thumbnail'])
        embed.add_field(name="Requested by", value=ctx.author.mention, inline=True)
        message = await ctx.send(embed=embed)
        await message.delete(delay=10)  # 10초 후 메시지 삭제

        # 패널 업데이트
        await update_panel(ctx)
    else:
        # 음악 큐가 비었을 경우 음성 채널 나가기
        await ctx.voice_client.disconnect()
        await send_embed(ctx, "종료", "모든 곡이 재생되어 봇이 음성 채널을 나갑니다.")
        current_tracks[guild_id] = None  # 현재 트랙 정보 초기화

@bot.command(name="일시정지")
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await send_embed(ctx, "음악 일시정지", "음악이 일시정지되었습니다.")

@bot.command(name="재개")
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await send_embed(ctx, "음악 재개", "음악이 재개되었습니다.")

@bot.command(name="스킵")
async def skip(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await send_embed(ctx, "음악 스킵", "현재 음악이 스킵되었습니다.")
        await play_music(ctx)

@bot.command(name="큐")
async def queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        queue_list = "\n".join([f"{idx + 1}. {song['title']}" for idx, song in enumerate(queues[guild_id])])
        embed = discord.Embed(title="현재 재생 목록", description=queue_list, color=0x1DB954)
        message = await ctx.send(embed=embed)
        await message.delete(delay=10)  # 10초 후 메시지 삭제
    else:
        await send_embed(ctx, "음악 큐", "큐에 음악이 없습니다.")

@bot.command(name="종료")
async def leave(ctx):
    if ctx.voice_client:  # 봇이 음성 채널에 연결되어 있을 때만 종료
        await ctx.voice_client.disconnect()
        await send_embed(ctx, "종료", "음성 채널에서 나갔습니다.")
    else:
        await send_embed(ctx, "종료 실패", "봇이 현재 음성 채널에 연결되어 있지 않습니다.")

# 패널을 위한 View와 Select 클래스
class MusicControlView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.add_item(MusicControlSelect())

class MusicControlSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="일시정지", description="현재 음악을 일시정지합니다"),
            discord.SelectOption(label="재개", description="일시정지된 음악을 재개합니다"),
            discord.SelectOption(label="스킵", description="현재 음악을 스킵합니다"),
            discord.SelectOption(label="큐", description="현재 음악 큐를 표시합니다"),
            discord.SelectOption(label="종료", description="봇을 음성 채널에서 퇴장시킵니다"),
        ]
        super().__init__(placeholder="원하는 명령어를 선택하세요", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        command = self.values[0]
        
        if command == "일시정지":
            await interaction.client.get_command("일시정지")(await interaction.client.get_context(interaction.message))
        elif command == "재개":
            await interaction.client.get_command("재개")(await interaction.client.get_context(interaction.message))
        elif command == "스킵":
            await interaction.client.get_command("스킵")(await interaction.client.get_context(interaction.message))
        elif command == "큐":
            await interaction.client.get_command("큐")(await interaction.client.get_context(interaction.message))
        elif command == "종료":
            await interaction.client.get_command("종료")(await interaction.client.get_context(interaction.message))

@bot.command(name="패널")
async def panel(ctx):
    global panel_messages
    guild_id = ctx.guild.id
    view = MusicControlView(guild_id)
    
    # 패널 설명 및 현재 재생 중인 곡 정보 추가
    embed = discord.Embed(title="음악 컨트롤 패널", description="음악 봇 기능 설명", color=0x1DB954)
    embed.add_field(name="현재 재생 중인 곡 정보", value="현재 재생 중인 노래의 제목과 앨범 커버", inline=False)
    embed.add_field(name="🎵 일시정지", value="현재 재생 중인 음악을 일시정지합니다.", inline=True)
    embed.add_field(name="▶️ 재개", value="일시정지된 음악을 다시 재생합니다.", inline=True)
    embed.add_field(name="⏭️ 스킵", value="현재 곡을 건너뛰고 다음 곡을 재생합니다.", inline=True)
    embed.add_field(name="📜 큐", value="현재 재생 대기 중인 곡 목록을 표시합니다.", inline=True)
    embed.add_field(name="🚪 종료", value="봇이 음성 채널에서 나가도록 합니다.", inline=True)
    
    # 현재 재생 중인 곡 정보가 있을 경우 추가
    if guild_id in current_tracks and current_tracks[guild_id]:
        embed.add_field(name="지금 재생 중", value=current_tracks[guild_id]['title'], inline=False)
        embed.set_thumbnail(url=current_tracks[guild_id]['thumbnail'])

    # 패널 메시지 전송 및 저장
    panel_messages[guild_id] = await ctx.send(embed=embed, view=view)

@bot.event
async def on_message(message):
    guild_id = message.guild.id

    # 봇 자신이 보낸 메시지에는 반응하지 않음
    if message.author == bot.user:
        return

    # 패널이 생성된 채널에서만 메시지 감지
    if panel_messages.get(guild_id) and message.channel == panel_messages[guild_id].channel and not message.content.startswith("!"):
        ctx = await bot.get_context(message)
        
        # 봇이 음성 채널에 연결되어 있지 않은 경우 사용자의 음성 채널에 연결
        if not ctx.voice_client:
            if message.author.voice:
                await message.author.voice.channel.connect()
            else:
                await send_embed(ctx, "연결 오류", "음성 채널에 연결되지 않았습니다.")
                return

        # 유튜브에서 검색 및 큐 추가
        search = message.content
        await send_embed(ctx, "검색 중", f"{search} 검색 중...")

        # 입력이 유튜브 링크인지 확인하고, 링크와 검색어에 따라 yt-dlp 사용 방식 분리
        if youtube_url_pattern.match(search):
            info = ytdl.extract_info(search, download=False)
        else:
            info = ytdl.extract_info(f"ytsearch:{search}", download=False)['entries'][0]
        
        if guild_id not in queues:
            queues[guild_id] = []
        queues[guild_id].append({'source': info['url'], 'title': info['title'], 'thumbnail': info['thumbnail']})
        await send_embed(ctx, "곡 추가됨", f"Added {info['title']} to the queue.")
        
        # 사용자가 보낸 메시지 삭제
        await message.delete(delay=10)  # 10초 후 삭제

        # 현재 재생 중인 음악이 없다면 재생
        if not ctx.voice_client.is_playing():
            await play_music(ctx)

    # 명령어도 계속 처리할 수 있도록 하기 위해 추가
    await bot.process_commands(message)


bot.run("MTMwNTQ1OTI0NjE1Mzk5MDE2NA.GbatHR.JS36eeVGgUA_TRxmsuBxRKL50C7v16ROvJr2dY")


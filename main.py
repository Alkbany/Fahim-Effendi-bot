import os
import discord
from discord import app_commands
from discord.ext import commands
import google.generativeai as genai

# إعداد الصلاحيات
intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # تسجيل الأوامر المائلة لتعمل فوراً
        await self.tree.sync()

bot = MyBot()

# سحب مفتاح جيميناي بأمان من الاستضافة
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-pro') # النسخة البرو الاحترافية

@bot.event
async def on_ready():
    print(f'تم تشغيل البوت بنجاح باسم: {bot.user}')

# أمر الذكاء الاصطناعي للإجابة على الأسئلة
@bot.tree.command(name="ask", description="اسأل ذكاء البوت الاصطناعي عن أي شيء")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        response = model.generate_content(question)
        await interaction.followup.send(response.text)
    except Exception as e:
        await interaction.followup.send("عذراً، حدث خطأ أثناء الاتصال بالذكاء الاصطناعي.")

# سحب توكن ديسكورد بأمان وتشغيل البوت
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(DISCORD_TOKEN)

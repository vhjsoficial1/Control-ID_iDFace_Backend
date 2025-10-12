from prisma import Prisma

db = Prisma()

async def connect_db():
    """Connect to database"""
    await db.connect()
    print("✅ Database connected")

async def disconnect_db():
    """Disconnect from database"""
    await db.disconnect()
    print("❌ Database disconnected")

async def get_db():
    """Dependency for getting database instance"""
    return db
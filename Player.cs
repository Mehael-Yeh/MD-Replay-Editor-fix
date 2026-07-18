using System;
using System.Collections.Generic;

namespace YgoMaster
{
    /// <summary>
    /// Minimal Player stub for standalone replay plugin.
    /// Only includes properties referenced by DuelSettings and DeckInfo.
    /// </summary>
    class Player
    {
        public uint Code;
        public string Name;
        public CardCollection Cards = new CardCollection();
        public bool IsViewingOwnReplays;
        public Dictionary<long, string> RecentlyListedReplayFilesByDid = new Dictionary<long, string>();
    }
}

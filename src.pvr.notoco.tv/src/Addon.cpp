#include "Client.h"

#include <kodi/AddonBase.h>

class ATTR_DLL_LOCAL NotocoAddon : public kodi::addon::CAddonBase
{
public:
  ADDON_STATUS CreateInstance(const kodi::addon::IInstanceInfo& instance, KODI_ADDON_INSTANCE_HDL& hdl) override
  {
    if (!instance.IsType(ADDON_INSTANCE_PVR))
      return ADDON_STATUS_UNKNOWN;
    hdl = new notoco::Client(instance);
    return ADDON_STATUS_OK;
  }

  // the client reads its settings when it starts
  ADDON_STATUS SetSetting(const std::string&, const kodi::addon::CSettingValue&) override
  {
    return ADDON_STATUS_NEED_RESTART;
  }
};

ADDONCREATOR(NotocoAddon)

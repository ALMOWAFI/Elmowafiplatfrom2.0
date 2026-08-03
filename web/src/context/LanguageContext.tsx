
import React, { createContext, useState, useContext, ReactNode } from 'react';

type Language = 'en' | 'ar';

type LanguageContextType = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};

const translations: Record<Language, Record<string, string>> = {
  en: {
    'home': 'Home',
    'planner': 'Travel Planner',
    'profile': 'Profile',
    'hero.title': 'Elmowafy Family Travels',
    'hero.subtitle': 'Discover our adventures around the world',
    'hero.cta': 'Plan Your Next Adventure',
    'explore': 'Explore Destinations',
    'recent': 'Recent Adventures',
    'chat.title': 'Travel Assistant',
    'chat.placeholder': 'Ask me about travel plans...',
    'chat.button': 'Send',
    'planner.title': 'Plan Your Next Journey',
    'planner.start': 'Where will you go next?',
    'footer.rights': 'All Rights Reserved',
    'viewMore': 'View More',
    'save': 'Save',
    'fromDate': 'From',
    'toDate': 'To',
    'destination': 'Destination',
    'notes': 'Notes',
    
    // Travel Challenges Feature Translations
    'travelChallenges.title': 'Family Travel Challenges',
    'travelChallenges.createChallenge': 'Create Challenge',
    'travelChallenges.createNewChallenge': 'Create New Challenge',
    'travelChallenges.activeChallenges': 'Active Challenges',
    'travelChallenges.upcomingChallenges': 'Upcoming Challenges',
    'travelChallenges.completedChallenges': 'Completed Challenges',
    'travelChallenges.topPlayers': 'Top Family Players',
    'travelChallenges.rank': 'Rank',
    'travelChallenges.player': 'Player',
    'travelChallenges.level': 'Level',
    'travelChallenges.points': 'Points',
    'travelChallenges.action': 'Action',
    'travelChallenges.viewProfile': 'View Profile',
    
    'challenge.title': 'Challenge Title',
    'challenge.arabicTitle': 'Arabic Title',
    'challenge.description': 'Description',
    'challenge.arabicDescription': 'Arabic Description',
    'challenge.titlePlaceholder': 'Enter challenge title',
    'challenge.arabicTitlePlaceholder': 'Enter Arabic title',
    'challenge.descriptionPlaceholder': 'Describe the challenge',
    'challenge.arabicDescriptionPlaceholder': 'Describe the challenge in Arabic',
    'challenge.type': 'Challenge Type',
    'challenge.types.treasureHunt': 'Treasure Hunt',
    'challenge.types.mafia': 'Mafia Game',
    'challenge.types.amongUs': 'Among Us',
    'challenge.types.quiz': 'Quiz Challenge',
    'challenge.types.photoChallenge': 'Photo Challenge',
    'challenge.types.custom': 'Custom Challenge',
    'challenge.judge': 'Challenge Judge',
    'challenge.selectJudge': 'Select a Judge',
    'challenge.points': 'Total Points',
    'challenge.startDate': 'Start Date',
    'challenge.endDate': 'End Date',
    'challenge.rules': 'Challenge Rules',
    'challenge.arabicRules': 'Arabic Rules',
    'challenge.rulesPlaceholder': 'Define the rules for this challenge',
    'challenge.arabicRulesPlaceholder': 'Define the rules in Arabic',
    'challenge.editChallenge': 'Edit Challenge',
    'challenge.createChallenge': 'Create Challenge',
    'challenge.updateChallenge': 'Update Challenge',
    'challenge.basicInfo': 'Basic Info',
    'challenge.teams': 'Teams',
    
    'status.upcoming': 'Upcoming',
    'status.active': 'Active',
    'status.completed': 'Completed',
    
    'teams.teamFormation': 'Team Formation',
    'teams.addTeam': 'Add Team',
    'teams.addNewTeam': 'Add New Team',
    'teams.createTeam': 'Create Team',
    'teams.englishName': 'English Name',
    'teams.arabicName': 'Arabic Name',
    'teams.teamNamePlaceholder': 'Enter team name',
    'teams.teamArabicNamePlaceholder': 'Enter Arabic team name',
    'teams.teamColor': 'Team Color',
    'teams.colorPreview': 'Team color preview',
    'teams.members': 'Team Members',
    'teams.noAvailableMembers': 'All family members have been assigned to teams',
    'teams.deleteTeam': 'Delete Team',
    'teams.removeMember': 'Remove Member',
    'teams.noTeamsYet': 'No teams have been created yet',
    'teams.createFirstTeam': 'Create First Team',
    
    'profile.playerProfile': 'Player Profile',
    'profile.memberNotFound': 'Family member not found',
    'profile.level': 'Level',
    'profile.points': 'pts',
    'profile.pointsToNextLevel': 'to next level',
    'profile.badges': 'Badges',
    'profile.noBadgesYet': 'No badges earned yet',
    'profile.achievements': 'Achievements',
    'profile.noAchievementsYet': 'No achievements earned yet',
    'profile.completedChallenges': 'Completed Challenges',
    
    'next': 'Next',
    'previous': 'Previous',
    'cancel': 'Cancel'
  },
  ar: {
    'home': 'الرئيسية',
    'planner': 'مخطط السفر',
    'profile': 'الملف الشخصي',
    'hero.title': 'رحلات عائلة الموافي',
    'hero.subtitle': 'اكتشف مغامراتنا حول العالم',
    'hero.cta': 'خطط لمغامرتك القادمة',
    'explore': 'استكشف الوجهات',
    'recent': 'المغامرات الأخيرة',
    'chat.title': 'مساعد السفر',
    'chat.placeholder': 'اسألني عن خطط السفر...',
    'chat.button': 'إرسال',
    'planner.title': 'خطط لرحلتك القادمة',
    'planner.start': 'إلى أين ستذهب بعد ذلك؟',
    'footer.rights': 'جميع الحقوق محفوظة',
    'viewMore': 'عرض المزيد',
    'save': 'حفظ',
    'fromDate': 'من',
    'toDate': 'إلى',
    'destination': 'الوجهة',
    'notes': 'ملاحظات',
    
    // Travel Challenges Feature Translations
    'travelChallenges.title': 'تحديات السفر العائلية',
    'travelChallenges.createChallenge': 'إنشاء تحدي',
    'travelChallenges.createNewChallenge': 'إنشاء تحدي جديد',
    'travelChallenges.activeChallenges': 'التحديات النشطة',
    'travelChallenges.upcomingChallenges': 'التحديات القادمة',
    'travelChallenges.completedChallenges': 'التحديات المكتملة',
    'travelChallenges.topPlayers': 'أفضل اللاعبين في العائلة',
    'travelChallenges.rank': 'المرتبة',
    'travelChallenges.player': 'اللاعب',
    'travelChallenges.level': 'المستوى',
    'travelChallenges.points': 'النقاط',
    'travelChallenges.action': 'إجراء',
    'travelChallenges.viewProfile': 'عرض الملف',
    
    'challenge.title': 'عنوان التحدي',
    'challenge.arabicTitle': 'العنوان بالعربية',
    'challenge.description': 'الوصف',
    'challenge.arabicDescription': 'الوصف بالعربية',
    'challenge.titlePlaceholder': 'أدخل عنوان التحدي',
    'challenge.arabicTitlePlaceholder': 'أدخل العنوان بالعربية',
    'challenge.descriptionPlaceholder': 'صف التحدي',
    'challenge.arabicDescriptionPlaceholder': 'صف التحدي بالعربية',
    'challenge.type': 'نوع التحدي',
    'challenge.types.treasureHunt': 'البحث عن الكنز',
    'challenge.types.mafia': 'لعبة المافيا',
    'challenge.types.amongUs': 'أمونج أس',
    'challenge.types.quiz': 'تحدي الأسئلة',
    'challenge.types.photoChallenge': 'تحدي الصور',
    'challenge.types.custom': 'تحدي مخصص',
    'challenge.judge': 'حكم التحدي',
    'challenge.selectJudge': 'اختر حكماً',
    'challenge.points': 'مجموع النقاط',
    'challenge.startDate': 'تاريخ البداية',
    'challenge.endDate': 'تاريخ النهاية',
    'challenge.rules': 'قواعد التحدي',
    'challenge.arabicRules': 'القواعد بالعربية',
    'challenge.rulesPlaceholder': 'حدد قواعد هذا التحدي',
    'challenge.arabicRulesPlaceholder': 'حدد القواعد بالعربية',
    'challenge.editChallenge': 'تعديل التحدي',
    'challenge.createChallenge': 'إنشاء تحدي',
    'challenge.updateChallenge': 'تحديث التحدي',
    'challenge.basicInfo': 'المعلومات الأساسية',
    'challenge.teams': 'الفرق',
    
    'status.upcoming': 'قادم',
    'status.active': 'نشط',
    'status.completed': 'مكتمل',
    
    'teams.teamFormation': 'تشكيل الفرق',
    'teams.addTeam': 'إضافة فريق',
    'teams.addNewTeam': 'إضافة فريق جديد',
    'teams.createTeam': 'إنشاء فريق',
    'teams.englishName': 'الاسم بالإنجليزية',
    'teams.arabicName': 'الاسم بالعربية',
    'teams.teamNamePlaceholder': 'أدخل اسم الفريق',
    'teams.teamArabicNamePlaceholder': 'أدخل اسم الفريق بالعربية',
    'teams.teamColor': 'لون الفريق',
    'teams.colorPreview': 'معاينة لون الفريق',
    'teams.members': 'أعضاء الفريق',
    'teams.noAvailableMembers': 'تم تعيين جميع أفراد العائلة للفرق',
    'teams.deleteTeam': 'حذف الفريق',
    'teams.removeMember': 'إزالة عضو',
    'teams.noTeamsYet': 'لم يتم إنشاء أي فرق حتى الآن',
    'teams.createFirstTeam': 'إنشاء الفريق الأول',
    
    'profile.playerProfile': 'ملف اللاعب',
    'profile.memberNotFound': 'لم يتم العثور على فرد العائلة',
    'profile.level': 'المستوى',
    'profile.points': 'نقطة',
    'profile.pointsToNextLevel': 'للمستوى التالي',
    'profile.badges': 'الشارات',
    'profile.noBadgesYet': 'لم يتم كسب أي شارات بعد',
    'profile.achievements': 'الإنجازات',
    'profile.noAchievementsYet': 'لم يتم تحقيق أي إنجازات بعد',
    'profile.completedChallenges': 'التحديات المكتملة',
    
    'next': 'التالي',
    'previous': 'السابق',
    'cancel': 'إلغاء'
  }
};

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguage] = useState<Language>('en');

  const t = (key: string): string => {
    return translations[language][key] || key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = (): LanguageContextType => {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

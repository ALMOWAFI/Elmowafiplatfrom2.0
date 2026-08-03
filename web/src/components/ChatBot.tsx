
import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useLanguage } from '@/context/LanguageContext';
import { MessageCircle, Send } from 'lucide-react';

type Message = {
  content: string;
  isBot: boolean;
};

const ChatBot = () => {
  const { language, t } = useLanguage();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { 
      content: language === 'en' 
        ? "Hello! I'm your Elmowafy family travel assistant. How can I help you plan your next adventure?" 
        : "مرحبًا! أنا مساعد سفر عائلة الموافي. كيف يمكنني مساعدتك في التخطيط لمغامرتك القادمة؟", 
      isBot: true 
    }
  ]);

  const handleSend = () => {
    if (!input.trim()) return;
    
    // Add user message
    setMessages(prev => [...prev, { content: input, isBot: false }]);
    
    // Simulate bot response
    setTimeout(() => {
      let response: string;
      
      if (input.toLowerCase().includes('egypt') || input.includes('مصر')) {
        response = language === 'en' 
          ? "Egypt is beautiful this time of year! The Elmowafy family visited Cairo last January. Would you like to see some recommendations from that trip?" 
          : "مصر جميلة في هذا الوقت من العام! زارت عائلة الموافي القاهرة في يناير الماضي. هل ترغب في رؤية بعض التوصيات من تلك الرحلة؟";
      } else if (input.toLowerCase().includes('joke') || input.includes('نكتة')) {
        response = language === 'en'
          ? "Why don't scientists trust atoms? Because they make up everything! 😄" 
          : "لماذا لا يثق العلماء بالذرات؟ لأنها تختلق كل شيء! 😄";
      } else {
        response = language === 'en'
          ? "That sounds like a great idea for your next family adventure! The Elmowafy travel collection has some recommendations that might help you plan this trip. Would you like me to show you?" 
          : "تبدو فكرة رائعة لمغامرتك العائلية القادمة! لدى مجموعة سفر الموافي بعض التوصيات التي قد تساعدك في التخطيط لهذه الرحلة. هل تريد مني أن أريك؟";
      }
      
      setMessages(prev => [...prev, { content: response, isBot: true }]);
    }, 1000);
    
    setInput('');
  };

  return (
    <Card className={`w-full max-w-md mx-auto shadow-lg border-primary/50 ${language === 'ar' ? 'rtl-text' : 'ltr-text'}`}>
      <CardHeader className="bg-primary text-white">
        <CardTitle className="flex items-center gap-2">
          <MessageCircle size={20} />
          {t('chat.title')}
        </CardTitle>
        <CardDescription className="text-white/80">
          {language === 'en' ? 'Your personal travel companion' : 'رفيق سفرك الشخصي'}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex flex-col h-80 overflow-y-auto p-4">
          {messages.map((message, index) => (
            <div 
              key={index} 
              className={`mb-3 max-w-[80%] ${message.isBot 
                ? 'bg-muted rounded-lg p-3 self-start' 
                : 'bg-primary text-white rounded-lg p-3 self-end'}`}
            >
              {message.content}
            </div>
          ))}
        </div>
      </CardContent>
      <CardFooter className="p-3 border-t">
        <div className="flex w-full gap-2">
          <Input
            placeholder={t('chat.placeholder')}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSend()}
          />
          <Button onClick={handleSend} size="icon">
            <Send size={18} />
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
};

export default ChatBot;

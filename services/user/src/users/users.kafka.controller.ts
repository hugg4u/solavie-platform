import { Controller, Logger } from '@nestjs/common';
import { EventPattern, Payload } from '@nestjs/microservices';
import { UsersService } from './users.service';

@Controller()
export class UsersKafkaController {
  private readonly logger = new Logger(UsersKafkaController.name);

  constructor(private readonly usersService: UsersService) {}

  @EventPattern('auth.events.user')
  async handleUserEvent(@Payload() message: any) {
    this.logger.log(`Received Kafka user event: ${JSON.stringify(message)}`);
    
    // Payload can be a raw Kafka message or a JSON object depending on deserializer
    let payload = message;
    if (message && typeof message === 'object' && 'value' in message) {
      payload = message.value;
    }
    
    if (typeof payload === 'string') {
      try {
        payload = JSON.parse(payload);
      } catch (e) {
        this.logger.error(`Failed to parse Kafka event payload: ${e.message}`);
        return;
      }
    }
    
    try {
      return await this.usersService.handleWebhookEvent(payload);
    } catch (e: any) {
      this.logger.error(`Error processing Kafka event for userId=${payload?.userId}: ${e.message}`);
    }
  }
}
